# Maintenance decisions

- 2026-09-10: Reproduced repeated write attempts and an unused total HTTP budget. Preserve the synchronous service API while using cancellable I/O and a bounded execution pool; retain each slot until its worker actually exits. Do not retry writes without a downstream idempotency contract. Verify with synthetic peers and loopback only; preserve existing deployment edits and identify the actual runtime before claiming production completion.
