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