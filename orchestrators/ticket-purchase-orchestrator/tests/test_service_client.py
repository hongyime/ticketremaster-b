"""HTTP reliability checks using synthetic peers and loopback sockets only."""
import asyncio
import json
import os
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import jwt
import pytest
from unittest.mock import MagicMock

import service_client as sc

REAL_CLIENT = httpx.AsyncClient


@pytest.fixture(autouse=True)
def isolated_client(monkeypatch):
    sc._circuit_breakers.clear()
    monkeypatch.setattr(sc, "TOTAL_TIMEOUT", 2)
    monkeypatch.setattr(sc, "RETRY_BACKOFF_FACTOR", 0)
    monkeypatch.setattr(sc.random, "uniform", lambda *_: 0)
    yield
    # Keep patches installed until cancelled peers have actually closed.
    for _ in range(sc.MAX_OUTSTANDING_CALLS):
        assert sc._http_slots.acquire(timeout=5), "HTTP fixture worker did not exit"
    for _ in range(sc.MAX_OUTSTANDING_CALLS):
        sc._http_slots.release()
    sc._circuit_breakers.clear()


@pytest.fixture
def peer(monkeypatch):
    def install(handler=None):
        # Build the transport before timed assertions. Its first construction
        # loads HTTPcore; these socket tests measure network waits, not imports.
        transport = httpx.MockTransport(handler) if handler else httpx.AsyncHTTPTransport(verify=False, trust_env=False)
        def client(**kwargs):
            return REAL_CLIENT(transport=transport, trust_env=False, verify=False, **kwargs)
        monkeypatch.setattr(sc.httpx, "AsyncClient", client)
    return install


@pytest.mark.parametrize("method", ["POST", "PATCH", "PUT", "DELETE"])
@pytest.mark.parametrize("failure", ["timeout", "connection", "server"])
def test_uncertain_writes_are_attempted_once(peer, method, failure):
    calls = []
    def handler(request):
        calls.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("lost response", request=request)
        if failure == "connection":
            raise httpx.ConnectError("unavailable", request=request)
        return httpx.Response(503, json={"error": {"code": "UPSTREAM_BUSY"}})
    peer(handler)
    result, error = sc.call_service(method, "http://fixture.invalid/write", json={"fixture": True})
    assert result is None and error
    assert len(calls) == 1
    assert json.loads(calls[0].content) == {"fixture": True}


def test_transient_read_status_retries_and_recovers(peer):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(503, json={"error": {"code": "BUSY"}}) if len(calls) == 1 else httpx.Response(200, json={"eventId": "fixture"})
    peer(handler)
    assert sc.call_service("GET", "http://fixture.invalid/events/one") == ({"eventId": "fixture"}, None)
    assert len(calls) == 2


@pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 429])
def test_client_error_is_not_retried_or_counted_as_service_failure(peer, status):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={"error": {"code": "INPUT_REJECTED"}})
    peer(handler)
    assert sc.call_service("GET", "http://fixture.invalid/events/one") == (None, "INPUT_REJECTED")
    assert len(calls) == 1
    assert next(iter(sc._circuit_breakers.values())).failure_count == 0


def test_retry_exhaustion_opens_one_circuit_for_different_paths(peer):
    calls = []
    def handler(request):
        calls.append(request)
        raise httpx.ConnectError("fixture connection failure", request=request)
    peer(handler)
    assert sc.call_service("GET", "http://fixture.invalid/events/one")[1] == "SERVICE_UNAVAILABLE"
    assert len(calls) == 3
    assert sc.call_service("GET", "http://fixture.invalid/events/two")[1] == "SERVICE_UNAVAILABLE"
    assert len(calls) == 3
    assert len(sc._circuit_breakers) == 1


def test_circuit_recovers_after_its_cooldown(peer, monkeypatch):
    cb = sc._get_circuit_breaker("http://fixture.invalid:80")
    cb.state = cb.OPEN
    cb.last_failure_time = time.monotonic() - cb.recovery_timeout - 1
    peer(lambda request: httpx.Response(200, json={"ok": True}))
    assert sc.call_service("GET", "http://fixture.invalid/status") == ({"ok": True}, None)
    assert cb.state == cb.CLOSED and cb.failure_count == 0


def test_total_budget_cancels_a_peer_waiting_for_headers(peer, monkeypatch):
    monkeypatch.setattr(sc, "TOTAL_TIMEOUT", 0.1)
    cancelled = []
    cancellation_finished = threading.Event()
    async def handler(request):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.append(True)
            cancellation_finished.set()
    peer(handler)
    start = time.monotonic()
    assert sc.call_service("GET", "http://fixture.invalid/hang") == (None, "SERVICE_UNAVAILABLE")
    assert time.monotonic() - start < 1
    assert cancellation_finished.wait(timeout=1)
    assert cancelled == [True]
    assert next(iter(sc._circuit_breakers.values())).failure_count == 1


def test_attempts_and_backoff_share_the_total_budget(peer, monkeypatch):
    monkeypatch.setattr(sc, "TOTAL_TIMEOUT", 0.5)
    monkeypatch.setattr(sc, "RETRY_BACKOFF_FACTOR", 0.05)
    calls = []
    cancelled = []
    cancellation_finished = threading.Event()
    async def handler(request):
        calls.append(request)
        try:
            await asyncio.sleep(0.3)
        except asyncio.CancelledError:
            cancelled.append(True)
            cancellation_finished.set()
            raise
        raise httpx.ReadTimeout("fixture wait", request=request)
    peer(handler)
    start = time.monotonic()
    assert sc.call_service("GET", "http://fixture.invalid/retry") == (None, "SERVICE_UNAVAILABLE")
    assert time.monotonic() - start < 1
    assert len(calls) == 2
    assert cancellation_finished.wait(timeout=1)
    assert cancelled == [True]


def test_backoff_that_cannot_fit_does_not_start_another_attempt(peer, monkeypatch):
    monkeypatch.setattr(sc, "TOTAL_TIMEOUT", 0.2)
    monkeypatch.setattr(sc, "RETRY_BACKOFF_FACTOR", 1)
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(503, json={"error": {"code": "BUSY"}})
    peer(handler)
    assert sc.call_service("GET", "http://fixture.invalid/retry") == (None, "BUSY")
    assert len(calls) == 1


class FixtureStream(httpx.AsyncByteStream):
    def __init__(self, chunks, delay=0):
        self.chunks = chunks
        self.delay = delay
        self.closed = False
        self.closed_event = threading.Event()

    async def __aiter__(self):
        for chunk in self.chunks:
            await asyncio.sleep(self.delay)
            yield chunk

    async def aclose(self):
        self.closed = True
        self.closed_event.set()


def test_slow_body_is_cancelled_and_closed(peer, monkeypatch):
    monkeypatch.setattr(sc, "TOTAL_TIMEOUT", 0.1)
    stream = FixtureStream([b" "] * 40, 0.02)
    peer(lambda request: httpx.Response(200, stream=stream))
    start = time.monotonic()
    assert sc.call_service("GET", "http://fixture.invalid/drip") == (None, "SERVICE_UNAVAILABLE")
    assert time.monotonic() - start < 1
    assert stream.closed_event.wait(timeout=1)
    assert stream.closed


def test_oversized_body_is_closed_without_retries(peer, monkeypatch):
    monkeypatch.setattr(sc, "MAX_RESPONSE_BYTES", 32)
    stream = FixtureStream([b" " * 20, b" " * 20])
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, stream=stream)
    peer(handler)
    assert sc.call_service("GET", "http://fixture.invalid/large") == (None, "SERVICE_UNAVAILABLE")
    assert stream.closed and len(calls) == 1


@pytest.mark.parametrize("body", [b"<html>upstream error</html>", b""])
def test_invalid_success_body_returns_the_error_contract(peer, body):
    peer(lambda request: httpx.Response(200, content=body))
    assert sc.call_service("GET", "http://fixture.invalid/invalid") == (None, "SERVICE_UNAVAILABLE")


def test_empty_successful_write_does_not_become_a_failure(peer):
    peer(lambda request: httpx.Response(204))
    assert sc.call_service("PATCH", "http://fixture.invalid/credits", json={"fixture": True}) == ({}, None)


def test_valid_json_null_preserves_the_success_contract(peer):
    peer(lambda request: httpx.Response(200, content=b"null"))
    assert sc.call_service("PATCH", "http://fixture.invalid/credits", json={"fixture": True}) == (None, None)


def test_write_redirect_is_not_followed(peer):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(307, headers={"Location": "http://other.invalid/write"})
    peer(handler)
    assert sc.call_service("POST", "http://fixture.invalid/write", follow_redirects=True) == (None, "SERVICE_UNAVAILABLE")
    assert len(calls) == 1


def test_credit_headers_and_timeout_preserve_the_callers_dictionary(peer, monkeypatch):
    monkeypatch.setenv("OUTSYSTEMS_API_KEY", "synthetic-api-key")
    monkeypatch.setenv("CREDIT_SERVICE_URL", "http://fixture.invalid/")
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"creditBalance": 42})
    peer(handler)
    headers = {"X-Request-ID": "fixture"}
    assert sc.call_credit_service("GET", "/credits/fixture", headers=headers, timeout=0.5) == ({"creditBalance": 42}, None)
    assert headers == {"X-Request-ID": "fixture"}
    assert calls[0].headers["X-API-KEY"] == "synthetic-api-key"
    assert calls[0].extensions["timeout"]["read"] == 0.5
    assert calls[0].extensions["timeout"]["connect"] == 0.5


def test_failure_logs_do_not_include_the_request_url_or_exception(peer, caplog):
    def handler(request):
        raise httpx.ConnectError("sensitive-fixture-value", request=request)
    peer(handler)
    sc.call_service("GET", "http://fixture.invalid/secret-path?token=sensitive-fixture-value")
    assert "sensitive-fixture-value" not in caplog.text
    assert "secret-path" not in caplog.text


def test_stalled_setup_is_bounded_and_cannot_fill_an_unbounded_work_queue(monkeypatch):
    monkeypatch.setattr(sc, "TOTAL_TIMEOUT", 0.1)
    release = threading.Event()
    started = []
    def blocked_runner(coroutine):
        # Simulate an OS resolver or client teardown that cannot finish yet.
        coroutine.close()
        started.append(True)
        release.wait(timeout=3)
        return None, "SERVICE_UNAVAILABLE"
    monkeypatch.setattr(sc.asyncio, "run", blocked_runner)
    try:
        for _ in range(sc.MAX_OUTSTANDING_CALLS):
            start = time.monotonic()
            assert sc.call_service("GET", "http://fixture.invalid/setup") == (None, "SERVICE_UNAVAILABLE")
            assert time.monotonic() - start < 0.8
        assert len(started) == sc.MAX_OUTSTANDING_CALLS
        start = time.monotonic()
        assert sc.call_service("GET", "http://fixture.invalid/refused") == (None, "SERVICE_UNAVAILABLE")
        assert time.monotonic() - start < 0.2
        assert len(started) == sc.MAX_OUTSTANDING_CALLS
    finally:
        release.set()


@contextmanager
def loopback_peer(mode):
    writes = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            try:
                self.send_response(200)
                self.send_header("Content-Length", "100")
                self.end_headers()
                for _ in range(100):
                    self.wfile.write(b" ")
                    self.wfile.flush()
                    time.sleep(0.02)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            writes.append("applied")
            try:
                time.sleep(0.3)
                self.send_response(204)
                self.end_headers()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/{mode}", writes
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)


def test_real_socket_slow_body_obeys_the_total_budget(peer, monkeypatch):
    peer()
    monkeypatch.setattr(sc, "TOTAL_TIMEOUT", 0.15)
    with loopback_peer("drip") as (url, _):
        start = time.monotonic()
        assert sc.call_service("GET", url, timeout=(1, 1)) == (None, "SERVICE_UNAVAILABLE")
        assert time.monotonic() - start < 1


def test_real_socket_lost_write_response_is_not_replayed(peer, monkeypatch):
    peer()
    monkeypatch.setattr(sc, "TOTAL_TIMEOUT", 0.15)
    with loopback_peer("write") as (url, writes):
        assert sc.call_service("POST", url, json={"fixture": True}) == (None, "SERVICE_UNAVAILABLE")
        assert writes == ["applied"]


@pytest.mark.parametrize("lost_response", [None, "ticket", "credit"])
def test_purchase_route_uses_the_real_http_helper_without_replaying_writes(client, peer, monkeypatch, lost_response):
    import routes
    stub = MagicMock()
    stub.SellSeat.return_value = MagicMock(success=True)
    monkeypatch.setattr(routes, "_grpc_stub", lambda: stub)
    monkeypatch.setattr(routes, "_get_cached_hold", lambda _: {
        "status": "held", "heldByUserId": "fixture-user", "holdToken": "fixture-hold",
        "heldUntil": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
    })
    monkeypatch.setattr(routes, "EVENT_SERVICE", "http://fixture.invalid/events-service")
    monkeypatch.setattr(routes, "TICKET_SERVICE", "http://fixture.invalid/ticket-service")
    monkeypatch.setattr(routes, "CREDIT_TXN_SERVICE", "http://fixture.invalid/ledger-service")
    monkeypatch.setenv("CREDIT_SERVICE_URL", "http://fixture.invalid/credit-service")
    calls = []
    def handler(request):
        calls.append((request.method, request.url.path))
        if request.method == "GET" and "/events/" in request.url.path:
            return httpx.Response(200, json={"price": 80, "venueId": "fixture-venue"})
        if request.method == "GET" and "/credits/" in request.url.path:
            return httpx.Response(200, json={"creditBalance": 200})
        if request.method == "POST" and request.url.path.endswith("/tickets"):
            if lost_response == "ticket":
                raise httpx.ReadTimeout("write applied; response lost", request=request)
            return httpx.Response(201, json={"ticketId": "fixture-ticket"})
        if request.method == "PATCH" and "/credits/" in request.url.path and lost_response == "credit":
            raise httpx.ReadTimeout("write applied; response lost", request=request)
        return httpx.Response(204)
    peer(handler)
    token = jwt.encode({"userId": "fixture-user", "role": "user", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)}, os.environ["JWT_SECRET"], algorithm="HS256")
    response = client.post("/purchase/confirm/fixture-inventory", json={"eventId": "fixture-event", "holdToken": "fixture-hold"}, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == (201 if lost_response is None else 500)
    assert calls.count(("POST", "/ticket-service/tickets")) == 1
    assert calls.count(("PATCH", "/credit-service/credits/fixture-user")) == (0 if lost_response == "ticket" else 1)
    assert calls.count(("POST", "/ledger-service/credit-transactions")) == (1 if lost_response is None else 0)
