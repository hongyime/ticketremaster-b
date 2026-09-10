"""
Shared HTTP helpers for all TicketRemaster orchestrators.
Implements timeout configuration, circuit breaker pattern, and retry logic.
"""
import asyncio
import json
import logging
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from threading import BoundedSemaphore, Lock
from urllib.parse import urlsplit

import httpx

logger = logging.getLogger(__name__)

# Timeout configuration (in seconds)
CONNECT_TIMEOUT = int(os.environ.get("CONNECT_TIMEOUT", "2"))
READ_TIMEOUT = int(os.environ.get("READ_TIMEOUT", "5"))
TOTAL_TIMEOUT = int(os.environ.get("TOTAL_TIMEOUT", "10"))
DEFAULT_TIMEOUT = (CONNECT_TIMEOUT, READ_TIMEOUT)
MAX_RESPONSE_BYTES = 1024 * 1024
RETRY_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
RETRY_STATUS_CODES = frozenset({500, 502, 503, 504})

# A caller must not wait for blocking client initialization or OS resolver
# cleanup after cancellation. Retain the slot until the worker actually exits,
# so repeated timeouts cannot create an unbounded queue of background calls.
MAX_OUTSTANDING_CALLS = 4
_http_pool = ThreadPoolExecutor(max_workers=MAX_OUTSTANDING_CALLS, thread_name_prefix="service-http")
_http_slots = BoundedSemaphore(MAX_OUTSTANDING_CALLS)

# Circuit breaker configuration
CIRCUIT_BREAKER_FAILURE_THRESHOLD = int(os.environ.get("CIRCUIT_BREAKER_FAILURE_THRESHOLD", "3"))
CIRCUIT_BREAKER_RECOVERY_SECONDS = int(os.environ.get("CIRCUIT_BREAKER_RECOVERY_SECONDS", "30"))
CIRCUIT_BREAKER_HALF_OPEN_MAX_REQUESTS = int(os.environ.get("CIRCUIT_BREAKER_HALF_OPEN_MAX_REQUESTS", "1"))

# Retry configuration
MAX_RETRIES = int(os.environ.get("HTTP_MAX_RETRIES", "2"))
RETRY_BACKOFF_FACTOR = float(os.environ.get("HTTP_RETRY_BACKOFF_FACTOR", "0.5"))


class CircuitBreaker:
    """
    Circuit breaker implementation for service calls.
    States: CLOSED (normal), OPEN (failing), HALF_OPEN (testing)
    """
    
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"
    
    def __init__(self, name, failure_threshold=CIRCUIT_BREAKER_FAILURE_THRESHOLD,
                 recovery_timeout=CIRCUIT_BREAKER_RECOVERY_SECONDS):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state = CircuitBreaker.CLOSED
        self.failure_count = 0
        self.last_failure_time = None
        self.half_open_successes = 0
        self._lock = Lock()
    
    async def call(self, func, *args, **kwargs):
        """Execute function with circuit breaker protection."""
        with self._lock:
            if self.state == CircuitBreaker.OPEN:
                if self._should_attempt_reset():
                    self.state = CircuitBreaker.HALF_OPEN
                    self.half_open_successes = 0
                    logger.info("Circuit breaker %s entering half-open state", self.name)
                else:
                    raise CircuitBreakerOpenError(f"Circuit breaker {self.name} is OPEN")
        
        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except asyncio.CancelledError:
            self._on_failure()
            raise
        except ServiceHTTPError as exc:
            # Invalid caller input does not mean the downstream is unavailable.
            if exc.status_code < 500:
                self._on_success()
            else:
                self._on_failure()
            raise
        except Exception:
            self._on_failure()
            raise
    
    def _should_attempt_reset(self):
        """Check if enough time has passed to attempt reset."""
        if self.last_failure_time is None:
            return True
        elapsed = time.monotonic() - self.last_failure_time
        return elapsed >= self.recovery_timeout
    
    def _on_success(self):
        """Handle successful call."""
        with self._lock:
            if self.state == CircuitBreaker.HALF_OPEN:
                self.half_open_successes += 1
                if self.half_open_successes >= CIRCUIT_BREAKER_HALF_OPEN_MAX_REQUESTS:
                    self.state = CircuitBreaker.CLOSED
                    self.failure_count = 0
                    logger.info("Circuit breaker %s closed after successful test", self.name)
            else:
                self.failure_count = 0
    
    def _on_failure(self):
        """Handle failed call."""
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.monotonic()
            
            if self.failure_count >= self.failure_threshold:
                self.state = CircuitBreaker.OPEN
                logger.warning("Circuit breaker %s opened after %d failures", self.name, self.failure_count)


# Global circuit breakers for each service
_circuit_breakers = {}
_cb_lock = Lock()


def _get_circuit_breaker(service_name):
    """Get or create circuit breaker for a service."""
    with _cb_lock:
        if service_name not in _circuit_breakers:
            _circuit_breakers[service_name] = CircuitBreaker(service_name)
        return _circuit_breakers[service_name]


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open."""
    pass


# Configurable timeout for OutSystems calls (default 5 seconds)
OUTSYSTEMS_TIMEOUT = int(os.environ.get("OUTSYSTEMS_TIMEOUT_SECONDS", "5"))


class ServiceHTTPError(Exception):
    """A downstream status and its bounded public error code."""

    def __init__(self, status_code, code):
        self.status_code = status_code
        self.code = code
        super().__init__(code)


class InvalidServiceResponse(Exception):
    """The response cannot be safely consumed as service JSON."""


def _error_code(body):
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        code = body["error"].get("code")
        if isinstance(code, str) and 0 < len(code) <= 128:
            return code
    return "SERVICE_UNAVAILABLE"


def _phase_timeout(value):
    # Keep the existing scalar and (connect, read) caller interface. Neither
    # value can disable the enclosing total budget.
    if isinstance(value, tuple):
        connect, read = value
    else:
        connect = read = value
    return httpx.Timeout(connect=connect, read=read, write=READ_TIMEOUT, pool=CONNECT_TIMEOUT)


async def _read_response(client, method, url, kwargs):
    async with client.stream(method, url, **kwargs) as response:
        body = bytearray()
        async for chunk in response.aiter_bytes():
            if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                raise InvalidServiceResponse("Response exceeds the byte limit")
            body.extend(chunk)
        try:
            payload = json.loads(body) if body else None
            decoded = bool(body)
        except (ValueError, UnicodeError):
            payload = None
            decoded = False
        if not response.is_success:
            raise ServiceHTTPError(response.status_code, _error_code(payload))
        if response.status_code in {204, 205} or method == "HEAD":
            return {}
        if not decoded:
            raise InvalidServiceResponse("Expected a JSON response")
        return payload


async def _call_service(method, url, deadline, kwargs):
    parsed = urlsplit(url)
    service_name = f"{parsed.scheme}://{parsed.hostname}:{parsed.port or (443 if parsed.scheme == 'https' else 80)}"
    cb = _get_circuit_breaker(service_name)
    attempts = max(0, MAX_RETRIES) + 1 if method in RETRY_METHODS else 1
    phase_timeout = _phase_timeout(kwargs.pop("timeout", DEFAULT_TIMEOUT))
    # API redirects are not part of the service contract. In particular, a
    # 307/308 must not automatically repeat a write or forward its API key.
    kwargs.pop("allow_redirects", None)
    kwargs.pop("follow_redirects", None)
    last_code = "SERVICE_UNAVAILABLE"
    async with asyncio.timeout(max(0, deadline - time.monotonic())):
        async with httpx.AsyncClient(timeout=phase_timeout, follow_redirects=False) as client:
            for attempt in range(attempts):
                if time.monotonic() >= deadline:
                    return None, "SERVICE_UNAVAILABLE"
                try:
                    result = await cb.call(_read_response, client, method, url, kwargs)
                    if time.monotonic() >= deadline:
                        return None, "SERVICE_UNAVAILABLE"
                    return result, None
                except CircuitBreakerOpenError:
                    return None, "SERVICE_UNAVAILABLE"
                except ServiceHTTPError as exc:
                    last_code = exc.code
                    if exc.status_code not in RETRY_STATUS_CODES:
                        return None, last_code
                except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError):
                    last_code = "SERVICE_UNAVAILABLE"
                except (httpx.HTTPError, InvalidServiceResponse):
                    return None, "SERVICE_UNAVAILABLE"
                if attempt + 1 >= attempts:
                    return None, last_code
                delay = RETRY_BACKOFF_FACTOR * (2 ** attempt) + random.uniform(0, 0.1)
                if delay >= deadline - time.monotonic():
                    return None, last_code
                logger.warning("Retrying read from %s after transient failure", service_name)
                await asyncio.sleep(max(0, delay))
    return None, last_code


def _run_service_call(method, url, deadline, kwargs):
    try:
        if time.monotonic() >= deadline:
            return None, "SERVICE_UNAVAILABLE"
        return asyncio.run(_call_service(method, url, deadline, kwargs))
    except TimeoutError:
        return None, "SERVICE_UNAVAILABLE"
    finally:
        _http_slots.release()


def call_service(method, url, **kwargs):
    """Return (JSON, None) or (None, error code) within one network budget.

    Only GET/HEAD/OPTIONS can retry. A failed write response does not establish
    whether the downstream write committed; callers must reconcile that state.
    """
    deadline = time.monotonic() + TOTAL_TIMEOUT
    if TOTAL_TIMEOUT <= 0 or not _http_slots.acquire(blocking=False):
        return None, "SERVICE_UNAVAILABLE"
    try:
        future = _http_pool.submit(_run_service_call, method.upper(), url, deadline, kwargs)
    except Exception:
        _http_slots.release()
        raise
    try:
        return future.result(timeout=max(0, deadline - time.monotonic()))
    except FutureTimeoutError:
        logger.warning("Service request exceeded its total network budget")
        return None, "SERVICE_UNAVAILABLE"


def call_credit_service(method, path, **kwargs):
    """
    Call the OutSystems Credit Service.
    Automatically injects the OUTSYSTEMS_API_KEY header.
    Uses configurable timeout from OUTSYSTEMS_TIMEOUT_SECONDS env var.
    """
    headers = dict(kwargs.pop("headers", {}))
    headers["X-API-KEY"] = os.environ["OUTSYSTEMS_API_KEY"]
    base = os.environ["CREDIT_SERVICE_URL"].rstrip("/")
    # Apply OutSystems-specific timeout if not already set
    kwargs.setdefault("timeout", OUTSYSTEMS_TIMEOUT)
    return call_service(method, f"{base}{path}", headers=headers, **kwargs)
