# AUDIT.md — ticketremaster-b

Generated: 20260524

## 0. FILESYSTEM HEALTH REPORT
No corrupted or orphaned files detected in tracked content.

## 1. MASTER FEATURE MAP
| File | Size |
|------|------|
| orchestrators/auth-orchestrator/app.py | 1309 bytes |
| orchestrators/auth-orchestrator/middleware.py | 3529 bytes |
| orchestrators/auth-orchestrator/routes.py | 13067 bytes |
| orchestrators/auth-orchestrator/service_client.py | 1715 bytes |
| orchestrators/auth-orchestrator/tests/__init__.py | 0 bytes |
| orchestrators/auth-orchestrator/tests/conftest.py | 578 bytes |
| orchestrators/auth-orchestrator/tests/test_auth_orchestrator.py | 6996 bytes |
| orchestrators/credit-orchestrator/app.py | 1028 bytes |
| orchestrators/credit-orchestrator/middleware.py | 1913 bytes |
| orchestrators/credit-orchestrator/routes.py | 10821 bytes |
| orchestrators/credit-orchestrator/service_client.py | 1715 bytes |
| orchestrators/credit-orchestrator/tests/__init__.py | 0 bytes |
| orchestrators/credit-orchestrator/tests/conftest.py | 458 bytes |
| orchestrators/credit-orchestrator/tests/test_credit_orchestrator.py | 5157 bytes |
| orchestrators/event-orchestrator/app.py | 1335 bytes |
| orchestrators/event-orchestrator/middleware.py | 2779 bytes |
| orchestrators/event-orchestrator/routes.py | 15834 bytes |
| orchestrators/event-orchestrator/service_client.py | 1962 bytes |
| orchestrators/event-orchestrator/tests/__init__.py | 0 bytes |
| orchestrators/event-orchestrator/tests/conftest.py | 458 bytes |
| orchestrators/event-orchestrator/tests/test_event_orchestrator.py | 5409 bytes |
| orchestrators/marketplace-orchestrator/app.py | 1044 bytes |
| orchestrators/marketplace-orchestrator/middleware.py | 1913 bytes |
| orchestrators/marketplace-orchestrator/routes.py | 10201 bytes |
| orchestrators/marketplace-orchestrator/service_client.py | 1962 bytes |
| orchestrators/marketplace-orchestrator/tests/__init__.py | 0 bytes |
| orchestrators/marketplace-orchestrator/tests/conftest.py | 458 bytes |
| orchestrators/marketplace-orchestrator/tests/test_marketplace_orchestrator.py | 8559 bytes |
| orchestrators/qr-orchestrator/app.py | 1019 bytes |
| orchestrators/qr-orchestrator/middleware.py | 1913 bytes |
| orchestrators/qr-orchestrator/routes.py | 7201 bytes |
| orchestrators/qr-orchestrator/service_client.py | 1962 bytes |
| orchestrators/qr-orchestrator/tests/__init__.py | 0 bytes |
| orchestrators/qr-orchestrator/tests/conftest.py | 458 bytes |
| orchestrators/qr-orchestrator/tests/test_qr_orchestrator.py | 6440 bytes |
| orchestrators/ticket-purchase-orchestrator/app.py | 2990 bytes |
| orchestrators/ticket-purchase-orchestrator/dlx_consumer.py | 2703 bytes |
| orchestrators/ticket-purchase-orchestrator/middleware.py | 1913 bytes |
| orchestrators/ticket-purchase-orchestrator/routes.py | 27779 bytes |
| orchestrators/ticket-purchase-orchestrator/seat_inventory_pb2_grpc.py | 9119 bytes |
| ... | +141 more files |

Total: 181 source files | Language: Python | Tests: none detected

## 2. RECONCILIATION SUMMARY
Documentation describes project purpose. Code implements described features.
Production Readiness: N/A (personal project)

## 3-5. GAPS / GHOSTS / DRIFT
No critical gaps identified between documentation and implementation.

## 6. DATA INTEGRITY
Database files present — read-only inspection only.

## 7. CODE QUALITY FINDINGS
No P0/P1 issues identified. See security_audit.md for detailed SAST/SCA results.

## 8. STRUCTURAL REORGANIZATION
Large project (181 files). Structure follows Python conventions.

## 9. PRODUCTION READINESS CHECKLIST
N/A — personal/educational project scope.

## 10. REMEDIATION ROADMAP
No critical remediation actions required. Ongoing dependency monitoring via Dependabot.

## 11. HTTP request diagnosis and maintenance plan — 2026-09-10

Status: implemented; local and hosted Python checks passed. Backend deployment remains unverified.

The ticket-purchase orchestrator declares `TOTAL_TIMEOUT=10` but never uses it. Its
request loop gives every attempt a fresh connect/read timeout and sleeps between
attempts. An isolated fake HTTP probe recorded three POST attempts and 22.5
simulated seconds. The helper is used for ticket creation, credit updates and
transaction logging (`routes.py:545`, `:568`, `:646`), with no helper-level
idempotency contract. Repeating an uncertain write can repeat a side effect.

`service_client.py` also checks `if exc.response` for server errors. Requests
responses with failing HTTP status are false-valued, so that condition prevents
the intended server-error retry. Invalid success JSON escapes the error contract,
and every response is read without a size limit. Requests connect/read timeouts
do not bound the complete response download, so merely reducing the timeout on
each retry would leave slowly arriving bodies unbounded.

Planned work, recorded before implementation:

- [x] Use one cancellable network budget across attempts, streamed body reads and
  backoff; bound decoded response size and close connections on all exits.
- [x] Retry only safe read methods and transient failures; make one attempt for
  writes, without automatic redirects. Preserve downstream error-code handling.
- [x] Verify timeout, slow-body, retry, body-limit, circuit and payment-adjacent
  workflows with synthetic responses; add a hosted Python check.
- [ ] Publish the reviewed source, preserve the 22 preexisting Docker/Compose
  edits, and verify the backend deployment when its runtime is identified.

This change does not establish end-to-end purchase idempotency. A lost write
response can still leave the downstream result unknown; the existing purchase
compensation/reconciliation workflow needs a separate transaction-level review.
No real payment, credit update, notification, database seed or cluster startup
is part of verification. The README describes a local Kubernetes/Cloudflare
backend; its current production runtime has not been identified.

References: [Requests timeout semantics](https://requests.readthedocs.io/en/latest/user/quickstart/#timeouts),
[HTTPX phase timeouts](https://www.python-httpx.org/advanced/timeouts/),
[Python cancellable timeout scope](https://docs.python.org/3/library/asyncio-task.html#asyncio.timeout).

The first timing probe also measured 2.58 seconds in cold HTTP-client
construction before any response read started. An asynchronous timeout alone
cannot preempt that synchronous initialization. A four-slot execution pool now
bounds the caller's wait independently; timed-out workers retain their slots
until cleanup actually finishes, preventing unbounded background admission.
The unused Requests dependency is removed from this orchestrator after checking
its source and imported shared modules; HTTPX supplies its transport.

Local verification passed 51 HTTP and purchase-route cases plus focused JSON
compatibility checks and Ruff. Fixtures cover response loss after a write,
safe-read recovery, downstream input errors, circuit recovery, a shared retry
budget, slow bodies, connection closure, oversized/malformed responses, 204 and
JSON-null success, header isolation, and four occupied execution slots refusing
additional work. Two peers use loopback sockets; other HTTP responses are
synthetic. No external provider, real transaction or existing database was used.

The hosted Python 3.12 workflow also passed on the complete implementation:
[Purchase HTTP checks](https://github.com/hongyime/ticketremaster-b/actions/runs/34487149343).
Production verification is still open: the configured local Kubernetes API
refused the read-only connection, and the backend runtime/deployment location
has been requested. Publishing source does not establish a running backend release.

### CodeQL configuration follow-up

The first main release triggered both default CodeQL and the custom
`.github/workflows/codeql.yml`. Default CodeQL passed with Python and Actions
coverage, while the custom Python analysis upload was rejected because default
setup was enabled. The custom workflow is now disabled in repository Actions
settings; its file and history remain intact. Default setup, its languages,
query suite and weekly schedule are unchanged. This removes the duplicate
automatic analysis without reducing the active language coverage. The earlier
failed upload remains in historical run 34487788524; the passing default scan is
run 34487787481. Do not re-enable the custom workflow alongside default setup.

Reference: [GitHub's default-setup upload conflict](https://docs.github.com/en/code-security/reference/code-scanning/sarif-files/troubleshoot-sarif-uploads/default-setup-enabled).
