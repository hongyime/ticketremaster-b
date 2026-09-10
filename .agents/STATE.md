# Current maintenance state

- Scope: ticket-purchase HTTP reliability; diagnosis and initial task list are in AUDIT.md section 11.
- Implementation: cancellable request/body/retry budget, four outstanding execution slots, bounded response bodies, read-only retries and no automatic redirects for writes. Other orchestrators are unchanged.
- Validation: 51 local HTTP/route checks and seven focused JSON/workflow checks passed; Ruff passed. Hosted Python 3.12 Purchase HTTP checks passed on implementation commit `22acdd675b7663f1b55340f7d78f0baebd818a83` (run 34487149343). The workflow also runs on main; deployment verification remains pending.
- Existing local Docker/Compose changes are preserved in the original checkout; work is isolated on `maintenance/ticket-http-20260910`.
- Deployment: the documented local Kubernetes endpoint is unavailable. Runtime location/deployment instructions were requested; no backend release, seed job or infrastructure startup has occurred.
- CI configuration: default CodeQL passed for Python and Actions. The duplicate custom `.github/workflows/codeql.yml` is disabled in Actions settings after its conflicting upload failed; default coverage and schedule remain unchanged. Keep one active CodeQL setup.
- Remaining: backend deployment verification. End-to-end purchase idempotency and uncertain-write reconciliation need a separate review. Portfolio release evidence records main publication and checks separately from this source checkout.
