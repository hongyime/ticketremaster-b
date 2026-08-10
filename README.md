# TicketRemaster Backend

TicketRemaster is a Kubernetes-first backend for event discovery, seat inventory, credit top-ups, ticket purchase, QR retrieval, staff verification, resale marketplace, and peer-to-peer ticket transfer.

The repository currently contains:

- 8 Flask orchestrators for browser-facing workflows
- 13 internal services and wrappers
- 1 Socket.IO notification service
- 10 PostgreSQL databases, each owned by a single service
- Redis for short-lived workflow state and locking support
- RabbitMQ for delayed and asynchronous workflow processing
- Kong 3.9 as the only browser-facing gateway
- Cloudflare Tunnel for optional public exposure of the local cluster
- committed Kubernetes manifests under `k8s/base`

## Current Stack

- Runtime: Python 3.12 on `python:3.12-slim`
- Web framework: Flask + Flasgger
- Persistence: PostgreSQL + Flask-SQLAlchemy + Flask-Migrate
- Gateway: Kong 3.9 in DB-less declarative mode
- Messaging: RabbitMQ 3 management image
- Cache and locks: Redis 7
- Internal RPC: gRPC for seat hold and sale operations
- Payments: Stripe wrapper service
- External system of record: OutSystems credit API
- OTP integration: OutSystems notification API wrapper
- Realtime: Flask-SocketIO + Redis Pub/Sub

## Architecture

TicketRemaster is deliberately split into layers that match the committed Kubernetes namespaces.

| Layer | Namespace | Owns |
| --- | --- | --- |
| Edge | `ticketremaster-edge` | Kong, cloudflared, gateway policy |
| Core | `ticketremaster-core` | Orchestrators, services, wrappers, seed jobs |
| Data | `ticketremaster-data` | PostgreSQL StatefulSets, Redis, RabbitMQ |

### Design Logic

- Orchestrators own browser-facing workflow composition and access control.
- Atomic services own a single bounded context and, where applicable, a dedicated database.
- Kong is the only supported browser ingress. Frontends should not call internal service DNS names or direct pod ports.
- OutSystems remains the source of truth for credit balance. `credit-transaction-service` is the internal ledger, not the balance authority.
- `seat-inventory-service` owns seat-state transitions and exposes gRPC for latency-sensitive hold, release, sell, and status checks.
- Redis is used for ephemeral state such as purchase hold cache and verification locks, not as the primary record of business data.
- RabbitMQ carries delayed hold expiry and transfer notification work so those flows are not tied to synchronous request latency.

## How to Start Backend: Complete Guide

This guide walks you through setting up the TicketRemaster backend from scratch. Choose your setup path:

- **Option 1: Local Development Only** - Run backend on your laptop with local port-forwarding (no internet exposure)
- **Option 2: Public Access via Cloudflare** - Expose your local backend to the internet for remote testing or frontend collaboration

### Prerequisites

Before starting, ensure you have these tools installed and Docker Desktop is running:

| Tool | Purpose | Verify Installation |
| --- | --- | --- |
| Docker Desktop | Container runtime (must be running) | `docker --version` |
| Minikube | Local Kubernetes cluster | `minikube version` |
| kubectl | Kubernetes CLI | `kubectl version --client` |
| Node.js | Required for Newman | `node --version` |
| Newman | API testing | `newman --version` |

**If Docker Desktop is not running:**

Start it from the Start menu and wait for the whale icon to stop animating, then verify:

```powershell
docker info
```

**If any other tools are missing, install them:**

Minikube: Download from <https://minikube.sigs.k8s.io/docs/start/> and run the installer

kubectl: Download from <https://kubernetes.io/docs/tasks/tools/install-kubectl-windows/> and place in your PATH

Newman:

```powershell
npm install -g newman
```

### First-Time Setup

#### 1. Configure Minikube Resources

Allocate enough memory and CPU for the backend stack:

```powershell
minikube config set memory 12288
minikube config set cpus 4
```

**If you're on Windows with WSL 2:**

Edit or create `C:\Users\<YourUsername>\.wslconfig`:

```ini
[wsl2]
memory=12GB
processors=4
```

Then restart WSL:

```powershell
wsl --shutdown
```

**Note:** If your machine has less than 16GB RAM, reduce memory to 8192 (8GB) but expect slower performance.

#### 2. Create the Secrets File

The backend requires a secrets file that contains API keys, database passwords, and other sensitive configuration.

Start from the example file and create your local secrets file at:

```powershell
Copy-Item k8s/base/secrets.local.yaml.example k8s/base/secrets.local.yaml
```

Then open `k8s/base/secrets.local.yaml` and fill in the required values yourself. This file is gitignored and should stay local to your machine.

The file typically contains:

- Cloudflare tunnel token (required for Option 2 only)
- OutSystems API keys for credit operations
- Database passwords
- Stripe and OTP wrapper secrets

**Troubleshooting:** Incorrect secrets can show up as `400` errors during registration, `401` errors during login, or database connection failures during startup.

#### 3. Start Minikube

Start your local Kubernetes cluster:

```powershell
minikube start
```

This will take 2-5 minutes on first run. Minikube will download the Kubernetes ISO, create a virtual machine, and configure kubectl.

Verify Minikube is running:

```powershell
minikube status
kubectl get nodes
```

You should see one node in "Ready" state.

**Troubleshooting:**

- If `minikube start` fails with "Exiting due to HOST_VIRT_UNAVAILABLE", enable virtualization in your BIOS
- If it fails with memory errors, reduce the memory allocation in step 1
- If it hangs, try `minikube delete` and then `minikube start` again

### Option 1: Local Development Setup (Localhost Only)

This setup runs the backend on your machine and exposes it only on `http://localhost:8000`. No internet exposure.

#### Start the Backend

Navigate to the `ticketremaster-b` directory and run:

```powershell
.\start-backend.bat
```

Choose your access mode (`Localhost only`, `Cloudflare only`, or `Both`), then choose how to handle data:

- `Continue current cluster data`: keep existing PVC-backed state when it still looks healthy
- `Restore repo DB snapshot`: replace the cluster databases from `db-snapshots/k8s/latest`
- `Fresh rebuild`: delete the Minikube cluster and recreate everything from scratch

If you prefer to bypass the batch wrapper, the direct PowerShell equivalent is:

```powershell
.\scripts\start_k8s.ps1 -DataMode Continue
```

The script will:

1. Check prerequisites (docker, kubectl, minikube, newman)
2. Verify Minikube is running
3. Build Docker images for all services (first run takes 10-15 minutes)
4. Load images into Minikube
5. Apply Kubernetes manifests
6. Wait for all pods to be ready (data plane → core services → edge gateway)
7. Run database seed jobs
8. Open a port-forward to Kong on `http://localhost:8000`
9. Run Newman smoke tests to verify everything works

Seeding is part of the normal startup flow in this mode.

**What to Expect:**

First run (with no images built):

- Total time: 15-20 minutes
- Most time is spent building Docker images

Subsequent runs (images already built):

- Total time: 3-5 minutes
- The script detects source changes and only rebuilds when needed

**Success indicators:**

- You'll see "Done" with the local gateway URL
- A minimized PowerShell window will stay open (this is the port-forward, don't close it)
- Newman tests will show green checkmarks
- Kong is available at `http://localhost:8000`

#### Verify It's Working

Test the gateway:

```powershell
Invoke-WebRequest http://localhost:8000/events
```

You should see JSON with event data.

Configure your frontend:

```env
VITE_API_BASE_URL=http://localhost:8000
VITE_KONG_API_KEY=tk_front_123456789
```

#### Troubleshooting

**Problem: Docker Desktop is not running**

Solution: Start Docker Desktop manually from the Start menu, wait for it to fully start, then run the script again.

**Problem: Minikube is not running**

Solution: Run `minikube start` and then retry the script.

**Problem: Build fails with "no space left on device"**

Solution: Clean up Docker and retry:

```powershell
docker system prune -a --volumes
```

**Problem: Pods stuck in "ImagePullBackOff"**

Solution: Rebuild and reload images:

```powershell
.\scripts\build_k8s_images.ps1
```

**Problem: Register returns 400, then login returns 401**

This means services weren't ready when seed jobs ran.

Solution: Re-run seed jobs:

```powershell
.\scripts\rerun_k8s_seeds.ps1
```

**Problem: Port 8000 is already in use**

The startup script will automatically find an available port and tell you which one it's using. Update your frontend config to use the new port.

**Problem: Port-forward window closes unexpectedly**

Solution: Restart it manually:

```powershell
kubectl port-forward -n ticketremaster-edge service/kong-proxy 8000:80
```

#### Advanced: Manual Control for Option 1 (Localhost)

Use this only if you want to bring up the localhost stack without `start-backend.bat` or `.\scripts\start_k8s.ps1`.

1. Start Minikube and verify the node is ready:

   ```powershell
   minikube start
   kubectl get nodes
   ```

2. Build the backend images and load them into Minikube:

   ```powershell
   .\scripts\build_k8s_images.ps1
   docker images --format "{{.Repository}}:{{.Tag}}" | Select-String "^ticketremaster/.+:local-k8s-20260329$" | ForEach-Object { minikube image load $_.Line.Trim() --overwrite=true }
   ```

3. Apply the Kubernetes manifests:

   ```powershell
   kubectl apply -k k8s/base
   ```

4. Wait for the data plane StatefulSets:

   ```powershell
   kubectl get statefulset -n ticketremaster-data -o name | ForEach-Object { kubectl rollout status $_ -n ticketremaster-data --timeout=300s }
   ```

5. Wait for the core deployments:

   ```powershell
   kubectl get deployment -n ticketremaster-core -o name | ForEach-Object { kubectl rollout status $_ -n ticketremaster-core --timeout=300s }
   ```

6. Wait for Kong:

   ```powershell
   kubectl rollout status deployment/kong -n ticketremaster-edge --timeout=300s
   ```

7. Wait for seed jobs to complete:

   ```powershell
   kubectl wait --for=condition=complete job --all -n ticketremaster-core --timeout=600s
   ```

   Both Option 1 and Option 2 use this same seed flow. Seeding happens before the localhost/public access choice matters.

   If you need to reseed later:

   ```powershell
   .\scripts\rerun_k8s_seeds.ps1
   ```

### Persisting Local Database State

If you want your local cluster data to survive a Minikube restart or PVC loss, keep a repo-local SQL snapshot of all 10 Postgres databases.

Create or refresh the snapshot:

```powershell
.\scripts\backup_k8s_db_snapshots.ps1
```

That writes SQL dumps to `db-snapshots/k8s/latest/`. Those files live inside the repo, so you can keep them locally or commit them if this is demo-only data that you intentionally want to recover later.

If you want scheduled backups, register the built-in Windows task:

```powershell
.\scripts\register_k8s_db_snapshot_task.ps1
```

By default it runs every 60 minutes and calls:

```powershell
.\scripts\backup_k8s_db_snapshots.ps1 -SkipIfTransientState
```

That `-SkipIfTransientState` guard avoids taking a snapshot while there are still live short-lived workflows such as:

- seat holds still in `held` state
- transfers still pending seller or buyer OTP before their 24-hour expiry

That way your regular snapshots favor stable states instead of freezing half-finished flows.

Restore the snapshot into a rebuilt cluster:

```powershell
.\scripts\restore_k8s_db_snapshots.ps1
```

Add `-SkipSeedJobs` if you want a raw restore without replaying the baseline seed jobs afterward.

The restore script now requires the full 10-database dump set, reloads every Postgres database dump, clears any expired transient state that should no longer be alive, then reruns the existing seed jobs so only baseline rows that are still missing get added back.

The automated startup flow now also checks `db-snapshots/k8s/latest/` when it detects wiped database state. If a snapshot exists, it restores that first and only falls back to plain reseeding when no snapshot is available.

8. Open the localhost gateway:

   ```powershell
   kubectl port-forward -n ticketremaster-edge service/kong-proxy 8000:80
   ```

9. Run the localhost smoke tests:

   ```powershell
   newman run postman/TicketRemaster.gateway.postman_collection.json -e postman/TicketRemaster.gateway-localhost.postman_environment.json --reporters cli
   ```

### Option 2: Public Access Setup (Cloudflare Tunnel)

This setup exposes your local backend to the internet via Cloudflare Tunnel, allowing you to access it from anywhere.

Useful for:

- Remote testing
- Sharing with frontend developers who don't want to run the backend
- Mobile device testing
- Accessing your backend from mobile devices

#### Additional Prerequisites

You need to set up your own Cloudflare Tunnel:

1. **Create a Cloudflare account** at <https://dash.cloudflare.com/sign-up> (free tier is sufficient)

2. **Add a domain to Cloudflare** (you can use a free domain from services like Freenom, or use your own domain)

3. **Create a Cloudflare Tunnel:**
   - Go to Zero Trust dashboard: <https://one.dash.cloudflare.com/>
   - Navigate to Networks → Tunnels
   - Click "Create a tunnel"
   - Choose "Cloudflared" as the connector type
   - Name your tunnel (e.g., "ticketremaster-backend")
   - Copy the tunnel token (starts with `eyJ...`)

4. **Configure the tunnel route:**
   - In the tunnel configuration, add a Public Hostname
   - Subdomain: Choose a subdomain (e.g., `api` or `ticketremaster-api`)
   - Domain: Select your domain
   - Service Type: `HTTP`
   - URL: `kong-proxy.ticketremaster-edge.svc.cluster.local:80`

5. **Add the tunnel token to your secrets file:**

   Edit `k8s/base/secrets.local.yaml` and add:

   ```yaml
   apiVersion: v1
   kind: Secret
   metadata:
     name: cloudflare-tunnel
     namespace: ticketremaster-edge
   type: Opaque
   stringData:
     CLOUDFLARE_TUNNEL_TOKEN: "your-tunnel-token-here"
   ```

6. **Update the Newman public environment file:**

   Edit `postman/TicketRemaster.gateway-public.postman_environment.json` and change the `gateway_url` value to your Cloudflare tunnel URL:

   ```json
   { "key": "gateway_url", "value": "https://your-subdomain.your-domain.com", "type": "default", "enabled": true }
   ```

#### Start the Backend with Public Access

Navigate to the `ticketremaster-b` directory and run:

```powershell
.\start-backend.bat
```

Choose:

- `2` for `Cloudflare only`
- `3` for `Both`

If you prefer to bypass the batch wrapper, the direct PowerShell equivalents are:

```powershell
# Both localhost and Cloudflare
.\scripts\start_k8s.ps1 -RunPublicTests

# Cloudflare only (no localhost port-forward)
.\scripts\start_k8s.ps1 -RunPublicTests -SkipPortForward
```

This does the same base startup and seeding as Option 1, then deploys the Cloudflare tunnel connector, waits for the tunnel to establish, and runs Newman smoke tests against the selected surfaces.

**If you only want the public URL (no local port-forward):**

```powershell
.\scripts\start_k8s.ps1 -RunPublicTests -SkipPortForward
```

**What to Expect:**

First run: 15-25 minutes (includes image building + tunnel connection time)

Subsequent runs: 4-6 minutes

**Success indicators:**

- Newman tests pass for both localhost and public URL
- Public gateway is accessible at your configured Cloudflare tunnel URL

#### Verify It's Working

Test the public gateway (replace with your actual tunnel URL):

```powershell
Invoke-WebRequest https://your-subdomain.your-domain.com/events
```

You should see JSON with event data.

Configure your frontend for public access (replace with your actual tunnel URL):

```env
VITE_API_BASE_URL=https://your-subdomain.your-domain.com
VITE_KONG_API_KEY=tk_front_123456789
```

#### Troubleshooting

**Problem: Cloudflare tunnel fails to connect**

Check the tunnel token in `secrets.local.yaml` is valid and not expired.

Check cloudflared logs:

```powershell
kubectl logs deployment/cloudflared -n ticketremaster-edge --tail=100
```

Solution: Restart the cloudflared deployment:

```powershell
kubectl rollout restart deployment/cloudflared -n ticketremaster-edge
```

**Problem: Public URL returns 502 Bad Gateway**

This means the tunnel is up but Kong is not ready yet.

Solution: Wait 1-2 minutes and try again. Check Kong logs:

```powershell
kubectl logs deployment/kong -n ticketremaster-edge --tail=100
```

**Problem: Public URL works intermittently**

The tunnel connector may be restarting.

Check cloudflared pod status:

```powershell
kubectl get pods -n ticketremaster-edge
```

If cloudflared pod is restarting, check its logs for errors.

**Problem: Public tests fail but localhost tests pass**

The tunnel may not be fully established yet.

Solution: Wait 2-3 minutes for the tunnel to stabilize, then run tests again:

```powershell
newman run postman/TicketRemaster.gateway.postman_collection.json -e postman/TicketRemaster.gateway-public.postman_environment.json --reporters cli
```

#### Advanced: Manual Add-On for Option 2 (Cloudflare)

Use this if you want the public setup without the automated wrapper.

1. Complete the Option 1 manual flow through the seed step. Both modes use the same seed jobs.
2. Wait for the Cloudflare connector:

   ```powershell
   kubectl rollout status deployment/cloudflared -n ticketremaster-edge --timeout=300s
   ```

3. Set the public tunnel URL in `postman/TicketRemaster.gateway-public.postman_environment.json`.
4. If you want both localhost and public access, keep the Kong port-forward running. If you want Cloudflare only, skip the port-forward.
5. Run the public smoke tests:

   ```powershell
   newman run postman/TicketRemaster.gateway.postman_collection.json -e postman/TicketRemaster.gateway-public.postman_environment.json --reporters cli
   ```

### Windows Helper Scripts

If you are using the Windows wrapper scripts, these are the main entry points:

- `.\start-backend.bat`: prompts for `Localhost only`, `Cloudflare only`, or `Both`, then asks whether to continue existing data, restore the repo snapshot, or rebuild fresh
- `.\test-backend.bat`: reruns gateway smoke tests against public, localhost, or both
- `.\check-status.bat`: prints pod status for `ticketremaster-core`, `ticketremaster-data`, and `ticketremaster-edge`, then checks the active localhost gateway URL and the public URL
- `.\stop-backend.bat`: stops local `kubectl` port-forwards and stops Minikube

### Checking Cluster Status

On Windows, the quickest summary is:

```powershell
.\check-status.bat
```

Or inspect things manually:

View all pods:

```powershell
kubectl get pods -n ticketremaster-edge
kubectl get pods -n ticketremaster-core
kubectl get pods -n ticketremaster-data
```

All pods should show "Running" status.

View seed jobs:

```powershell
kubectl get jobs -n ticketremaster-core
```

All jobs should show "1/1" completions.

View logs for a specific service:

```powershell
kubectl logs deployment/auth-orchestrator -n ticketremaster-core --tail=100
kubectl logs deployment/user-service -n ticketremaster-core --tail=100
```

Access RabbitMQ management UI:

```powershell
kubectl port-forward -n ticketremaster-data service/rabbitmq 15672:15672
```

Then open `http://localhost:15672` in your browser (username: `guest`, password: `guest`).

### Stopping the Backend

Stop port-forward: Close the PowerShell window running the port-forward, or press `Ctrl+C`.

Stop Minikube (preserves data):

```powershell
minikube stop
```

Delete Minikube (removes all data):

```powershell
minikube delete
```

Use `minikube delete` if you want a completely fresh start or if you're having persistent issues.

### Common Issues and Solutions

**Issue: Everything was working, now nothing works after restart**

Cause: Minikube's persistent volumes were wiped and the cluster no longer has the expected seed data.

If you use the automated startup flow (`.\start-backend.bat` or `.\scripts\start_k8s.ps1`), it now tries to detect missing seed data and restore `db-snapshots/k8s/latest/` first. If no repo snapshot exists, it falls back to reseeding automatically.

If you want to keep your local state between cluster rebuilds, take a fresh snapshot before shutting down:

```powershell
.\scripts\backup_k8s_db_snapshots.ps1
```

To restore that state later:

```powershell
.\scripts\restore_k8s_db_snapshots.ps1
```

If you need to reseed manually, run:

```powershell
.\scripts\rerun_k8s_seeds.ps1
```

Or delete and reapply the jobs:

```powershell
kubectl delete job seed-venues seed-events seed-seats seed-seat-inventory seed-users -n ticketremaster-core
kubectl apply -k k8s/base
kubectl wait --for=condition=complete job --all -n ticketremaster-core --timeout=600s
```

**Issue: Services are crashing with database connection errors**

Cause: Database passwords in `secrets.local.yaml` don't match what the databases expect.

Solution: Verify the values in `k8s/base/secrets.local.yaml` are correct. If the PostgreSQL volumes were already created with different passwords, recreate the cluster data and start again:

```powershell
minikube delete
minikube start
```

Then rerun the normal startup flow.

### Notes About Seeding Safety

The committed seed jobs already work in a missing-row-only style for the baseline reference data:

- venues are keyed by fixed `venueId` values like `ven_001`
- events are keyed by fixed `eventId` values like `evt_001`
- seats are backfilled only when a `(venueId, seatNumber)` pair is missing
- seat inventory is backfilled only when an `(eventId, seatId)` pair is missing
- demo users are skipped when the seeded email already exists

Most business tables in this repo also use string or UUID primary keys instead of integer autoincrement keys, so replaying seeds after a snapshot restore does not create the usual sequence drift problems you would expect from serial IDs.

**Issue: Out of disk space**

Cause: Docker images and Minikube volumes accumulate over time.

Solution: Clean up Docker:

```powershell
docker system prune -a --volumes
minikube delete
minikube start
```

Then rebuild:

```powershell
.\scripts\build_k8s_images.ps1
```

**Issue: Minikube won't start after Windows update**

Cause: Windows updates sometimes break virtualization or Docker.

Solution:

1. Restart Docker Desktop
2. Try `minikube delete` then `minikube start`
3. If still failing, reinstall Minikube

**Issue: Newman tests fail with timeout errors**

Cause: Services are still starting up or are overloaded.

Solution: Wait 1-2 minutes and run tests again:

```powershell
newman run postman/TicketRemaster.gateway.postman_collection.json -e postman/TicketRemaster.gateway-localhost.postman_environment.json --reporters cli
```

## Public and Local Surfaces

- **Local gateway:** `http://localhost:8000` (when port-forward is active)
- **Public gateway:** Your configured Cloudflare tunnel URL (e.g., `https://api.yourdomain.com`)
- **RabbitMQ management:** `http://localhost:15672` (after port-forwarding `svc/rabbitmq`)

Frontends should use the no-prefix routes such as `/auth/login` and `/events`. Kong also supports `/api/...` compatibility aliases, but new frontend code should use the no-prefix form.

## Browser-Facing Routes

| Route group | Current paths |
| --- | --- |
| Auth | `/auth/register`, `/auth/verify-registration`, `/auth/login`, `/auth/me`, `/auth/logout`, `/auth/logout-all` |
| Events and venues | `/venues`, `/events`, `/events/{eventId}`, `/events/{eventId}/seats`, `/events/{eventId}/seats/{inventoryId}`, `/admin/events`, `/admin/events/{eventId}/dashboard` |
| Credits | `/credits/balance`, `/credits/topup/initiate`, `/credits/topup/confirm`, `/credits/topup/webhook`, `/credits/transactions` |
| Purchase | `/purchase/hold/{inventoryId}`, `DELETE /purchase/hold/{inventoryId}`, `/purchase/confirm/{inventoryId}` |
| Tickets and QR | `/tickets`, `/tickets/{ticketId}/qr` |
| Marketplace | `/marketplace`, `/marketplace/list`, `DELETE /marketplace/{listingId}` |
| Transfer | `/transfer/initiate`, `/transfer/pending`, `/transfer/{transferId}`, `/transfer/{transferId}/seller-accept`, `/transfer/{transferId}/seller-reject`, `/transfer/{transferId}/buyer-verify`, `/transfer/{transferId}/seller-verify`, `/transfer/{transferId}/resend-otp`, `/transfer/{transferId}/cancel` |
| Staff verification | `/verify/scan`, `/verify/manual` |
| Stripe ingress | `/webhooks/stripe` |

## Development Workflow

### Making Code Changes

After modifying service or orchestrator code:

Rebuild images:

```powershell
.\scripts\build_k8s_images.ps1
```

Restart affected deployments:

```powershell
# Restart specific service
kubectl rollout restart deployment/user-service -n ticketremaster-core

# Or restart all core services
kubectl rollout restart deployment -n ticketremaster-core
```

Wait for rollout to complete:

```powershell
kubectl rollout status deployment/user-service -n ticketremaster-core
```

The startup script automatically detects code changes and rebuilds images when needed.

### Running Tests

The repository includes Newman smoke tests that verify the gateway and all major workflows.

Run localhost tests:

```powershell
newman run postman/TicketRemaster.gateway.postman_collection.json -e postman/TicketRemaster.gateway-localhost.postman_environment.json --reporters cli
```

Run public tests:

```powershell
newman run postman/TicketRemaster.gateway.postman_collection.json -e postman/TicketRemaster.gateway-public.postman_environment.json --reporters cli
```

### Viewing Service Documentation

Each service exposes Swagger/Flasgger documentation at its `/apidocs` endpoint.

To access it:

Port-forward to the service:

```powershell
kubectl port-forward -n ticketremaster-core deployment/user-service 5000:5000
```

Open `http://localhost:5000/apidocs` in your browser.

## For Frontend Developers

If you only need to consume the backend and don't want to run it locally, you have two options:

**Option A: Use a shared backend instance**

If your team has a shared backend instance running with a Cloudflare tunnel, use that URL:

```env
VITE_API_BASE_URL=https://your-team-backend-url.com
VITE_KONG_API_KEY=tk_front_123456789
```

**Option B: Set up your own Cloudflare tunnel**

Follow the instructions in "Option 2: Public Access Setup" above to expose your local backend to the internet.

**Note:** Shared backend instances should not be used for destructive testing or load testing.

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
