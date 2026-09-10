# Current maintenance state

- Scope: ticket-purchase HTTP reliability; diagnosis and initial task list are in AUDIT.md section 11.
- Implementation: cancellable request/body/retry budget, four outstanding execution slots, bounded response bodies, read-only retries and no automatic redirects for writes. Other orchestrators are unchanged.
- Validation: 51 local HTTP/route checks passed after adding the execution guard; JSON success compatibility was then checked separately. Ruff passed. Hosted checks and deployment verification remain pending.
- Existing local Docker/Compose changes are preserved in the original checkout; work is isolated on `maintenance/ticket-http-20260910`.
- Deployment: the documented local Kubernetes endpoint is unavailable. Runtime location/deployment instructions were requested; no backend release, seed job or infrastructure startup has occurred.
- Remaining: finish focused checks, hosted Python verification, source publication and deployment verification. End-to-end purchase idempotency and uncertain-write reconciliation need a separate review.
