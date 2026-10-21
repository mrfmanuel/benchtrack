# BenchTrack

[![CI](https://github.com/mrfmanuel/benchtrack/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/mrfmanuel/benchtrack/actions/workflows/ci.yml)
[![CD](https://github.com/mrfmanuel/benchtrack/actions/workflows/cd.yml/badge.svg)](https://github.com/mrfmanuel/benchtrack/actions/workflows/cd.yml)

A lightweight repair-ticket tracker for a single small computer-repair shop, with a protected staff area and a public tracking page.

> 🚧 Work in progress — runs locally and in Docker Compose, with CI on every push and pull request; the production deployment comes next.

## Problem

Small independent computer-repair shops (one technician, a bench, a WhatsApp number) track repairs in notebooks, chat threads and memory. This causes three recurring problems:

1. **Lost context** — the technician forgets what was diagnosed, which parts were ordered, or what price was quoted.
2. **Constant "is it ready yet?" messages** — customers have no way to check status, so they call or message repeatedly.
3. **No overview** — it is hard to see at a glance which devices are waiting for parts, which are ready for pickup, and which have been sitting on the bench for too long.

## Solution

- **Staff area** (protected by a staff token): register customers and repair tickets, move tickets through a fixed status workflow, add notes, print a receipt with the tracking code, and see a dashboard of open and stale work.
- **Public tracking page** (no login, `/track`): a customer enters the tracking code from their receipt (e.g. `BT-7K3QX`) and sees the current status and a timeline — without any personal data, notes or costs.

See [`product-spec.md`](product-spec.md) for the full scope, including what is out of scope for v1.

## Quick start (Docker Compose)

Requirements: Docker with Compose v2. One image serves the API and the built frontend; PostgreSQL runs next to it.

```powershell
Copy-Item .env.example .env
# Edit .env: set STAFF_TOKEN to a random value of 16+ characters, e.g. from
#   python -c "import secrets; print(secrets.token_urlsafe(32))"
docker compose up --build -d --wait          # builds the image, runs migrations, waits until healthy
docker compose exec app python -m app.seed   # optional fictional demo data
```

Open http://localhost:8000 and sign in with your `STAFF_TOKEN`. The public tracking page is http://localhost:8000/track (try `BT-DEM22` after seeding) and the API docs are at http://localhost:8000/docs.

- The app is published on `127.0.0.1` only (not reachable from other devices on your network). Port 8000 busy? Set `APP_PORT=8010` in `.env` (or `$env:APP_PORT = "8010"`) and open that port instead.
- `docker compose logs -f app` shows JSON logs (tracking codes masked). `docker compose down` keeps the data in the `pgdata` volume; only `docker compose down -v` deletes it.
- Compose sets `DATABASE_URL` (to the `db` service) and `LOG_FORMAT=json` for the app, overriding `.env`.

## Configuration

Copy `.env.example` to `.env` (never commit `.env`).

| Variable | Description | Default |
|----------|-------------|---------|
| `STAFF_TOKEN` | Bearer token for staff endpoints. Required; the app refuses to start if it is shorter than 16 characters. | — |
| `DATABASE_URL` | SQLAlchemy URL. SQLite for local dev/tests, PostgreSQL in Compose/production. | `sqlite:///./benchtrack.db` |
| `LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR` | `INFO` |
| `LOG_FORMAT` | `text` or `json` (`json` in Compose/production) | `text` |
| `FRONTEND_DIST` | Built SPA directory to serve from FastAPI (set in the Docker image to `/app/frontend/dist`). Unset in development, where Vite serves the frontend. | — |
| `PORT` | Port uvicorn listens on inside the container | `8000` |
| `CLIENT_IP_HEADER` | Header the edge proxy overwrites with the client IP, used by the public rate limit (Render: `CF-Connecting-IP`). Unset: the TCP peer. `X-Forwarded-For` is rejected (clients can forge it). | — |
| `APP_VERSION` | Version reported by `GET /api/health` (CI and CD use the commit SHA); falls back to `RENDER_GIT_COMMIT`, set by Render | `dev` |
| `APP_PORT` | Compose only: host port published for the app | `8000` |
| `VITE_SHOP_NAME` | Build-time shop name on receipts and in the header (public, not a secret) | `BenchTrack Repair` |

## Running locally

Requirements: Python 3.12 with [uv](https://docs.astral.sh/uv/), Node.js 20+ (developed on 24), optionally Docker for PostgreSQL.

**Backend** (http://127.0.0.1:8000, API docs at `/docs`):

```powershell
cd backend
uv run alembic upgrade head
uv run python -m app.seed          # optional fictional demo data
uv run uvicorn app.main:app --reload
```

**Frontend** (http://localhost:5173), in a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 and sign in with your `STAFF_TOKEN`. Customers track repairs at http://localhost:5173/track. The Vite dev server proxies `/api` and `/docs` to `http://127.0.0.1:8000`; if the backend runs elsewhere, set `$env:API_PROXY_TARGET = "http://127.0.0.1:8001"` before `npm run dev`. The shop name on receipts comes from `VITE_SHOP_NAME` (see `frontend/.env.example`).

| Command (in `frontend/`) | What it does |
|---|---|
| `npm test` | Vitest + Testing Library (lib, API client, components, pages) |
| `npm run lint` | oxlint |
| `npm run typecheck` | `tsc -b` |
| `npm run build` | type-check and production build into `frontend/dist/` |

Tests: see [`docs/testing.md`](docs/testing.md) for every layer, its command and test count. Database options: [`docs/database.md`](docs/database.md).

## CI/CD

- [`ci.yml`](.github/workflows/ci.yml) runs on pull requests and pushes to `main`: Redocly contract lint, backend ruff + unit/API tests, PostgreSQL integration tests, frontend lint/test/build, a Docker image smoke test and Semgrep (results uploaded as an artifact).
- [`cd.yml`](.github/workflows/cd.yml) runs after CI succeeds on `main`: it calls the Render deploy hook and waits up to ~10 minutes until `APP_URL/api/health` reports `status: ok` **and** `version` equal to the commit CI tested, so a still-running old instance cannot pass the check. Configure it under *Settings → Secrets and variables → Actions*: secret `RENDER_DEPLOY_HOOK_URL`, variable `APP_URL`. Until the secret exists, nothing is deployed and the run shows a **NOT DEPLOYED** warning; re-run it after adding the secret. Setup and troubleshooting: [`docs/deployment.md`](docs/deployment.md).

## Documentation

- [`product-spec.md`](product-spec.md) — product scope and behavior (source of truth)
- [`openapi.yaml`](openapi.yaml) — API contract
- [`AGENTS.md`](AGENTS.md) — instructions for coding agents and contributors
- [`docs/database.md`](docs/database.md) — database environments, migrations, seeding, ER diagram
- [`docs/testing.md`](docs/testing.md) — test pyramid, commands and counts, CI jobs
- [`docs/deployment.md`](docs/deployment.md) — Render setup, free-tier limits, deploy troubleshooting
- [`ops/runbook.md`](ops/runbook.md) — start/stop, health and version, logs, deploy and rollback, seeding, token rotation
- [`ops/incidents/`](ops/incidents/) — incident reports
- [`security/`](security/README.md) — PR audit, scans and triage, agent security notes, AI tool and data policy
- [`docs/ai-workflow.md`](docs/ai-workflow.md) — AI-assisted development log
