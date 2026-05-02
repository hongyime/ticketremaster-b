# PRD: ticketremaster-b (Backend)

## Overview
A Kubernetes-first microservices backend for a comprehensive event ticketing platform. Handles event discovery, seat inventory management, credit top-ups, ticket purchase, QR code retrieval, staff verification, a resale marketplace, and peer-to-peer ticket transfer. Eight Flask orchestrators coordinate 13+ internal services, connected via RabbitMQ for async workflows and Redis for short-lived state. Kong 3.9 serves as the sole API gateway.

## Goals
- Complete ticketing lifecycle: browse events → select seats → purchase → receive QR → verify at gate
- Credit-based payment system with Stripe top-up
- P2P ticket transfer and resale marketplace
- Real-time notifications via Socket.IO
- 10 isolated PostgreSQL databases (one per service)
- Kubernetes deployment with committed manifests
- Kong API gateway with Cloudflare Tunnel for public exposure

## Non-Goals
- Frontend (see ticketremaster-f)
- Third-party ticketing API integration
- Mobile native apps

## User Stories
- As a buyer, I want to browse events, select specific seats, purchase tickets with credits, and receive a QR code.
- As a reseller, I want to list my purchased tickets on the marketplace and transfer ownership on sale.
- As staff, I want to scan and verify QR codes at the venue gate.
- As an admin, I want to create events and manage seating.

## Tech Stack
- **Language**: Python 3.x
- **Framework**: Flask (8 orchestrators)
- **Database**: PostgreSQL 18-alpine (10 databases, one per service)
- **Cache/State**: Redis
- **Message Queue**: RabbitMQ (delayed + async workflows)
- **API Gateway**: Kong 3.9
- **Notifications**: Socket.IO service
- **Payments**: Stripe
- **Container**: Docker Compose (dev) + Kubernetes (prod)
- **Tunnel**: Cloudflare Tunnel (optional public exposure)

## Architecture
```
ticketremaster-b/
├── services/                  # 13+ internal services
│   ├── user-service/          # Auth, profiles
│   ├── event-service/         # Event catalog
│   ├── inventory-service/     # Seat availability + locking
│   ├── payment-service/       # Credit ledger, Stripe
│   ├── ticket-service/        # Ticket issuance + QR
│   ├── verification-service/  # Staff QR scan
│   ├── transfer-service/      # P2P ticket transfer
│   ├── marketplace-service/   # Resale listings
│   ├── notification-service/  # Socket.IO push
│   └── ...
├── api-gateway/               # Kong config
├── k8s/base/                  # Kubernetes manifests
├── docker-compose.yml         # Local dev stack
├── .postman/                  # API test collections
├── pytest.ini
└── mypy.ini
```

**Services map:**
| Service | Database | Port |
|---------|----------|------|
| user-service | user_service_db | 5000 |
| event-service | event_service_db | — |
| inventory-service | inventory_service_db | — |
| payment-service | payment_service_db | — |
| ticket-service | ticket_service_db | — |
| verification-service | verification_service_db | — |
| transfer-service | transfer_service_db | — |
| marketplace-service | marketplace_service_db | — |
| notification-service | (Redis) | — |
| + orchestrators | — | — |

## Workflow: Ticket Purchase
1. User selects event + seats → inventory-service locks seats (Redis TTL)
2. User completes payment → payment-service deducts credits (or Stripe charge)
3. On payment success → RabbitMQ message → ticket-service issues ticket + QR
4. QR stored in DB; user retrieves via ticket-service
5. At gate: staff scans QR → verification-service marks ticket used

## Environment Variables
Each service reads from shared `.env`:
- `POSTGRES_USER`, `POSTGRES_PASSWORD`
- Service-specific `DATABASE_URL`s
- `REDIS_URL`
- `RABBITMQ_URL`
- `STRIPE_SECRET_KEY`
- Kong admin credentials

## Deployment / Run
```bash
# Local dev
docker compose up -d

# Check service status
python check-status.bat

# Tests
pytest

# Kubernetes
kubectl apply -f k8s/base/
```

## Constraints & Notes
- **10 databases**: each service owns its DB — no cross-service foreign keys
- **RabbitMQ delayed queues**: used for time-bounded seat lock expiry and delayed notification delivery
- **Kong 3.9**: declarative config for all routes, auth plugins, rate limiting
- **Cloudflare Tunnel**: allows public testing without port forwarding; see Cloudflare dashboard for configuration
- **Kubernetes manifests**: committed under `k8s/base/`; overlay-style (Kustomize or raw manifests)
