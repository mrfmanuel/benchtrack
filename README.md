# BenchTrack

[![CI](https://github.com/mrfmanuel/benchtrack/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/mrfmanuel/benchtrack/actions/workflows/ci.yml)
[![CD](https://github.com/mrfmanuel/benchtrack/actions/workflows/cd.yml/badge.svg)](https://github.com/mrfmanuel/benchtrack/actions/workflows/cd.yml)

A repair-ticket tracker for one small computer-repair shop: a staff area for customers, tickets and a status workflow, and a public page where customers check their repair with the code on their receipt.

**Live demo:** https://benchtrack.onrender.com · **API docs:** https://benchtrack.onrender.com/docs · **Task tracker:** [GitHub Issues](https://github.com/mrfmanuel/benchtrack/issues)

## Contents

[Problem and solution](#problem-and-solution) · [Live demo](#live-demo) · [Screenshots](#screenshots) · [Features](#features) · [Architecture](#architecture) · [Quick start](#quick-start-docker-compose) · [Local development](#local-development-without-docker) · [Tests](#tests) · [CI/CD and deployment](#cicd-and-deployment) · [API contract](#api-contract) · [AI-assisted workflow](#ai-assisted-workflow) · [Security and operations](#security-and-operations) · [Agent extension pack](#agent-extension-pack) · [Repo map](#repo-map) · [Known limitations](#known-limitations)

## Problem and solution

Small independent computer-repair shops (one technician, a bench, a WhatsApp number) track repairs in notebooks, chat threads and memory. That causes three recurring problems:

1. **Lost context:** the technician forgets what was diagnosed, which parts were ordered or what price was quoted.
2. **Constant "is it ready yet?" messages:** customers have no way to check the status, so they call or message again and again.
3. **No overview:** it is hard to see which devices are waiting for parts, which are ready for pickup and which have sat on the bench too long.

**BenchTrack** fixes this with one small web app:

- **Staff area** (protected by a staff token): register customers and repair tickets, move tickets through a fixed status workflow with a timeline, add internal notes, print a receipt with a tracking code, and see a dashboard of open and stale work.
- **Public tracking page** (no login): the customer types the code from the receipt, e.g. `BT-7K3QX`, and sees the current status and its history. It never shows personal data, notes, costs or internal IDs.

The full scope, acceptance scenarios and every decision taken during development are in [`product-spec.md`](product-spec.md) (§9 "Clarifications and decisions" wins over §1–8). Open work is tracked as [GitHub Issues](https://github.com/mrfmanuel/benchtrack/issues) with acceptance criteria; the tracker started on 2026-10-21, and earlier work is logged step by step in [`docs/ai-workflow.md`](docs/ai-workflow.md).

## Live demo

- **Public tracking (no login):** https://benchtrack.onrender.com/track/BT-DEM22. Other demo codes: `BT-DEM28` (ready for pickup), `BT-DEM2A` (delivered), `BT-DEM2C` (cancelled).
- **Staff area:** it needs a staff token, which is not published. Evaluate it with [Docker Compose](#quick-start-docker-compose) (about 2 minutes, your own token and the same demo data) or through the [screenshots](#screenshots).
- **Health and version:** https://benchtrack.onrender.com/api/health shows the deployed commit.
- **Cold start:** the app runs on Render's free tier and sleeps when idle. The first request can take **about a minute**; after that it is fast.

All data in the demo, the seed and the screenshots is fictional.

## Screenshots

Captured from the local Compose app with freshly seeded demo data by [`scripts/capture_screenshots.py`](scripts/capture_screenshots.py) (Playwright). The staff token is never shown.

| Dashboard | Tickets list |
|---|---|
| ![Dashboard with counts for all 7 statuses and the stale-tickets list](docs/screenshots/dashboard.png) | ![Ticket list with search and status filter](docs/screenshots/tickets.png) |
| **Ticket detail with timeline** | **Printable receipt** |
| ![Ticket detail: details, status change, notes and timeline](docs/screenshots/ticket-detail.png) | ![Receipt with the tracking code and the tracking URL](docs/screenshots/receipt.png) |
| **Public tracking page (no login)** | **Dashboard at mobile width** |
| ![Public tracking for BT-DEM28: status, progress and history only](docs/screenshots/tracking.png) | <img src="docs/screenshots/dashboard-mobile.png" alt="Dashboard on a 390 px wide screen" width="260"> |

## Features

| Area | What it does |
|---|---|
| Customers | Create, search (name or phone), view and edit. Phones are normalized (`+506 8800-1234` → `+50688001234`) and unique; a duplicate returns `409` with a link to the existing customer. |
| Tickets | Device type, brand, model, serial, reported issue, diagnosis, estimated cost in CRC (₡). Search by code, customer, brand or model; filter by status; paginated. |
| Status workflow | `received → diagnosing → (waiting_parts ⇄ repairing) → ready → delivered`, with shortcuts (`diagnosing → ready`, `ready → repairing`) and `cancelled` from any status before `ready`. Invalid moves return `409` listing the allowed next statuses. Delivered and cancelled tickets are read-only, but notes can still be added. |
| Timeline | Every status change and note is an event with a timestamp. |
| Receipt | Print view with the shop name, customer, device, issue, tracking code and tracking URL. |
| Dashboard | Counts for all 7 statuses and **stale tickets**: open tickets not updated for more than 7 days, oldest first. |
| Public tracking | `/track/<code>`: case-insensitive, `BT-` prefix optional. Returns a fixed whitelist of 7 fields, rate-limited to 10 lookups per minute per client. |
| Unguessable codes | `BT-` + 5 characters from a 30-character alphabet without look-alikes (0/O, 1/I/L, U), generated with `secrets`. |
| Operations | `/api/health` with database check and deployed version, JSON logs with masked tracking codes, security headers (CSP, HSTS, …). |

## Architecture

```mermaid
flowchart LR
  subgraph Users
    staff["Staff browser<br/>(token in localStorage)"]
    customer["Customer browser<br/>(tracking code only)"]
  end

  subgraph Container["Docker image (one container)"]
    api["FastAPI + uvicorn<br/>/api/* JSON API · /docs<br/>serves the React SPA build"]
  end
  db[("PostgreSQL 16")]

  staff -- "HTTPS · Bearer token" --> api
  customer -- "HTTPS · /track/BT-…" --> api
  api -- "SQLAlchemy 2 + Alembic" --> db

  subgraph GitHub
    pr["Pull request / push to main"] --> ci["CI: 7 jobs<br/>(contract, backend, integration,<br/>frontend, docker, semgrep, agent pack)"]
    ci -- "success on main" --> cd["CD workflow"]
  end
  cd -- "POST deploy hook" --> render["Render: build Dockerfile,<br/>alembic upgrade head, start"]
  render --> api
  cd -. "poll /api/health until<br/>version == commit SHA" .-> api
```

One image serves both the API and the built single-page app, so there is no CORS and one deploy unit. The contract-first flow, request path, data model, containers and the CI/CD pipeline are explained in [`docs/architecture.md`](docs/architecture.md).

| Piece | Technology | Role |
|---|---|---|
| Frontend | React 19, TypeScript, Vite, React Router | Staff SPA and public tracking page. All HTTP goes through one module, `frontend/src/api/client.ts`, typed from the contract. |
| Backend | Python 3.12, FastAPI, Pydantic v2 | JSON API implementing `openapi.yaml`: thin routers, service layer, one error envelope, bearer auth, rate limit, security headers. Also serves the SPA build. |
| Database | PostgreSQL 16 (SQLite for quick local dev and unit tests) | Customers, tickets, ticket events. SQLAlchemy 2 ORM, Alembic migrations run on every container start. |
| API contract | OpenAPI 3.1 (`openapi.yaml`), Redocly lint, Swagger UI at `/docs` | Single source of truth for backend and frontend; parity tests keep the app and the contract identical. |
| Packaging | uv (Python), npm (Node), multi-stage Dockerfile, Docker Compose | Reproducible installs from lockfiles; one non-root image; Compose runs app + database locally. |
| Tests | pytest, httpx TestClient, Vitest, Testing Library | Unit, API, PostgreSQL integration and frontend tests. |
| CI/CD | GitHub Actions | CI on every PR and push to `main`; CD deploys after green CI and verifies the deployed commit. |
| Hosting | Render (Docker web service + Render PostgreSQL), behind Cloudflare | Production at https://benchtrack.onrender.com. |
| Security tooling | Semgrep, pip-audit, npm audit, gitleaks, Trivy, actionlint | Deterministic scans; findings triaged in `security/`. |
| AI tooling | Claude Code (CLI), Claude in Chrome | Built with AI assistance; see [AI-assisted workflow](#ai-assisted-workflow). |

## Quick start (Docker Compose)

Requirements: [Docker](https://docs.docker.com/get-docker/) with Compose v2, and Git. The commands work the same in Windows PowerShell and in a Linux/macOS shell.

```bash
git clone https://github.com/mrfmanuel/benchtrack.git
cd benchtrack
cp .env.example .env
```

Open `.env` in an editor and set `STAFF_TOKEN` to a random value of at least 16 characters (the app refuses to start with the placeholder). Any long random string works, for example one from a password manager or from `python -c "import secrets; print(secrets.token_urlsafe(32))"`.

```bash
docker compose up --build -d --wait
docker compose exec app python -m app.seed
```

The first command builds the image, starts PostgreSQL and the app, runs the migrations and waits until both are healthy. The second loads the fictional demo data (safe to run twice).

- **Staff area:** http://localhost:8000 → sign in with your `STAFF_TOKEN`.
- **Public tracking:** http://localhost:8000/track/BT-DEM22
- **API docs:** http://localhost:8000/docs · **health:** http://localhost:8000/api/health

Notes:
- **Port busy?** The app uses host port 8000 and PostgreSQL 5433, so another app or another Compose stack can already hold them. Set `APP_PORT` (e.g. `8010`) and/or `DB_PORT` (e.g. `5434`) in `.env`, run `docker compose up -d --wait` again, and use the new app port in the browser. If you change `DB_PORT`, use the same port in `TEST_DATABASE_URL` for the integration tests.
- The app and the database are published on `127.0.0.1` only, not on your network.
- `docker compose logs -f app` shows JSON logs. `docker compose down` keeps the data in the `pgdata` volume; `docker compose down -v` deletes it.

## Local development (without Docker)

Requirements: Python 3.12 with [uv](https://docs.astral.sh/uv/), Node.js 20+ (developed on 24). Uses SQLite by default; see [`docs/database.md`](docs/database.md) for PostgreSQL.

`cp .env.example .env` as above and set `STAFF_TOKEN`. Then the backend (http://127.0.0.1:8000):

```bash
cd backend
uv run alembic upgrade head
uv run python -m app.seed
uv run uvicorn app.main:app --reload
```

And the frontend in a second terminal (http://localhost:5173, proxies `/api` and `/docs` to the backend):

```bash
cd frontend
npm ci
npm run dev
```

Open http://localhost:5173 and sign in with your `STAFF_TOKEN`.

<details>
<summary>Configuration (all variables are in <code>.env.example</code>)</summary>

| Variable | Description | Default |
|---|---|---|
| `STAFF_TOKEN` | Bearer token for staff endpoints. Required, at least 16 characters. | — |
| `DATABASE_URL` | SQLAlchemy URL: SQLite for local dev, PostgreSQL in Compose and production (Compose sets it). | `sqlite:///./benchtrack.db` |
| `LOG_LEVEL` / `LOG_FORMAT` | Logging level; `text` or `json` (`json` in Compose and production). | `INFO` / `text` |
| `CLIENT_IP_HEADER` | Header the edge proxy overwrites with the client IP, for the public rate limit (Render: `CF-Connecting-IP`). Never `X-Forwarded-For` (refused). | TCP peer |
| `APP_VERSION` | Version shown by `/api/health`; falls back to `RENDER_GIT_COMMIT`, then `dev`. | `dev` |
| `APP_PORT` | Compose only: host port for the app. | `8000` |
| `DB_PORT` | Compose only: host port for PostgreSQL (`127.0.0.1`). | `5433` |
| `VITE_SHOP_NAME` | Build-time shop name for the header and receipts. | `BenchTrack Repair` |
| `FRONTEND_DIST` | Built SPA directory served by FastAPI (set in the image). | — |
| `TEST_DATABASE_URL` | PostgreSQL database for integration tests; its name must end in `_test`. | — |

</details>

## Tests

**Everything with one command** (repo root; starts the Compose PostgreSQL for the integration tests, prints a PASS/FAIL summary):

```bash
uv run --no-project python scripts/test_all.py
```

Add `--skip-integration` to run without Docker. Or run each layer on its own:

| Layer | Count | Command (from) |
|---|---|---|
| Backend unit + API (one command) | 549 | `uv run pytest` (`backend/`) |
| Backend integration (real PostgreSQL) | 10 | `uv run pytest -m integration` (`backend/`, needs `TEST_DATABASE_URL`) |
| Frontend (Vitest + Testing Library) | 145 | `npm test` (`frontend/`) |
| Contract lint | — | `npx @redocly/cli@2.66.0 lint openapi.yaml` (repo root) |
| Agent pack: hooks, sync script, MCP server | 35 + 9 + 25 | see [`docs/testing.md`](docs/testing.md) |

Unit and API tests need nothing else. Integration tests run against the Compose PostgreSQL; their database is dropped and recreated, so its name must end in `_test`:

```bash
docker compose up -d db --wait
cd backend
```

```powershell
# Windows PowerShell
$env:TEST_DATABASE_URL = "postgresql+psycopg://benchtrack:benchtrack@127.0.0.1:5433/benchtrack_test"
uv run pytest -m integration
```

```bash
# Linux / macOS
export TEST_DATABASE_URL="postgresql+psycopg://benchtrack:benchtrack@127.0.0.1:5433/benchtrack_test"
uv run pytest -m integration
```

(Or put `TEST_DATABASE_URL` in `.env`. Replace `5433` if you set `DB_PORT`.) The test pyramid, what each layer covers and the CI jobs are in [`docs/testing.md`](docs/testing.md).

## CI/CD and deployment

- **CI** ([`ci.yml`](.github/workflows/ci.yml)) runs on every pull request and push to `main`, in 7 jobs: Redocly contract lint; backend ruff + unit/API tests; PostgreSQL integration tests (the job fails if any test is skipped); frontend lint, tests and build; Docker image build + smoke test of the real container; Semgrep; and the agent pack (hook, sync-script and MCP tests). Actions are pinned to commit SHAs with read-only permissions.
- **Uptime** ([`uptime.yml`](.github/workflows/uptime.yml)) checks production every 15 minutes and opens an `alert` issue when users would be affected ([`ops/alerting.md`](ops/alerting.md)).
- **CD** ([`cd.yml`](.github/workflows/cd.yml)) runs only after CI succeeds on `main`. It calls the Render deploy hook, then polls `/api/health` until `version` equals the commit CI tested, so an old instance can't pass the check. If the deploy secret is missing, the run is flagged **NOT DEPLOYED** instead of passing silently.
- **`main` is protected** by a GitHub ruleset: changes only through pull requests, all 7 checks required, no force pushes. A human merges.
- **Rollback:** redeploy the previous good commit from Render's deploy history ([runbook §4](ops/runbook.md#4-deploy-and-rollback)).

Render setup, environment variables, free-tier limits and troubleshooting: [`docs/deployment.md`](docs/deployment.md).

## API contract

[`openapi.yaml`](openapi.yaml) (OpenAPI 3.1) is the source of truth and was written before the backend. It defines 14 operations, every error code, and the public whitelist.

- Browse it at **`/docs`** (Swagger UI, rendered from that file) locally or at https://benchtrack.onrender.com/docs. The raw file is served at `/api/openapi.yaml`.
- Contract parity tests (`backend/tests/api/test_contract.py`) fail if an operation, operationId or success status differs between the app and the file; Redocly lints it in CI.
- Every error uses one envelope: `{"error": {"code": "...", "message": "...", "details": ...}}`.

## AI-assisted workflow

BenchTrack was built with **Claude Code** as the coding agent and a human maintainer reviewing, testing and approving every step. [`docs/ai-workflow.md`](docs/ai-workflow.md) logs each step: the prompt, what was delegated, the manual review and how it was verified.

- **Context files:** [`AGENTS.md`](AGENTS.md) (rules for all agents; [`CLAUDE.md`](CLAUDE.md) points to it), [`product-spec.md`](product-spec.md), [`openapi.yaml`](openapi.yaml).
- **Process:** spec first → spec review by the agent (open questions answered in spec §9) → contract → test-first backend → frontend → containers → CI/CD → production → audits. One commit per task, tests with every change. Since 2026-10-21 every change starts from an [issue](https://github.com/mrfmanuel/benchtrack/issues); its PR says `Closes #N` and ticks the acceptance criteria with evidence.
- **Agent team:** the human maintainer, a planner/reviewer agent (Claude in Cowork), the implementer (Claude Code) and a read-only `contract-reviewer` subagent. Roles, hand-offs and rules are in [`docs/agent-team.md`](docs/agent-team.md).
- **Who did what:** the agents wrote code, tests and docs. The human made the product decisions, ran and checked the app, set up accounts and secrets, approved production actions and merged. Production actions needed an explicit "yes".
- **AI tools:** Claude Code CLI, Claude in Chrome for UI checks and read-only production diagnosis, and a read-only MCP server for the API (see below). Data rules: [`security/ai-tool-data-policy.md`](security/ai-tool-data-policy.md).

## Security and operations

- [`security/README.md`](security/README.md) indexes everything: the PR #1 security audit (including a real rate-limit bypass found and fixed), deterministic scans and their triage (Semgrep, pip-audit, npm audit, gitleaks, Trivy), agent security notes and the AI tool and data policy.
- [`ops/runbook.md`](ops/runbook.md): start/stop, health and version, logs, deploy and rollback, seeding, rotating the staff token, free-tier limits.
- [`ops/alerting.md`](ops/alerting.md): a synthetic check of health and the public tracking journey every 15 minutes; it opens an `alert` issue on failure and closes it on recovery.
- [`ops/incidents/`](ops/incidents/): a real incident report (a deploy that didn't apply), with root cause and the changes that followed.

## Agent extension pack

Claude Code extensions that keep AI agents working the BenchTrack way, scoped to this repository:

- **Skills:** `contract-first-endpoint` (the end-to-end workflow for an API change) and `release-check` (the pre-PR gate).
- **Subagent:** `contract-reviewer`, read-only, reports drift between `openapi.yaml`, the backend and the frontend.
- **Guard hooks:** a PreToolUse guard blocks `.env` access, `rm -rf`, force pushes, pushes to `main`, `DROP TABLE` and printing secrets. A PostToolUse hook runs ruff after Python edits.
- **MCP server:** read-only `benchtrack` MCP server (health, dashboard, tickets, tracking).
- **Plugin:** everything above packaged as the `benchtrack-dev` plugin, plus permission rules (allow/ask/deny).

They load automatically in a Claude Code session started in the repo. Details and live evidence: [`docs/agent-extension-pack.md`](docs/agent-extension-pack.md). What agents may and may not do: [`docs/permissions.md`](docs/permissions.md).

## Repo map

```text
.
├── README.md, product-spec.md, openapi.yaml   overview, scope (source of truth), API contract
├── AGENTS.md, CLAUDE.md                       instructions for coding agents
├── backend/          FastAPI app (app/: routers, services, models, schemas), Alembic migrations, tests (unit, api, integration)
├── frontend/         React + TypeScript SPA (src/api: the only HTTP layer; pages, components, lib), Vitest tests
├── Dockerfile, docker/, docker-compose.yml    image (SPA build + API, non-root), entrypoint, health check, local stack
├── .github/workflows/  ci.yml (7 jobs), cd.yml (deploy + verify), uptime.yml (alert)
├── docs/             architecture, agent-team, ai-workflow, testing, database, deployment, agent-extension-pack, permissions, self-review, screenshots/
├── security/         PR audit, scan findings and raw outputs, agent security notes, AI tool and data policy
├── ops/              runbook, alerting, incidents/
├── agent-capabilities/  skills and the contract-reviewer subagent (sources)
├── agent-hooks/      guard and ruff hooks + tests
├── mcp-server/       read-only BenchTrack MCP server + tests
├── plugins/          benchtrack-dev plugin, sync script + tests
├── .claude/          Claude Code project settings, synced skills and subagent
└── scripts/          test_all.py (every test suite, one command), uptime_check.py (alert), capture_screenshots.py
```

## Known limitations

- **One staff role, one shared token**, stored in the browser's localStorage. There are no user accounts, roles or audit trail of who changed what (by design for v1, spec §5).
- **The rate limit is in memory**, so it only works with a single instance (v1 runs one).
- **Free hosting:** about 1 minute of cold start after idle time, and the free Render PostgreSQL expires about 30 days after creation unless upgraded ([deployment](docs/deployment.md#free-tier-limits)).
- **One environment:** CD deploys straight to production after green CI. There is no staging environment or manual promotion step ([#11](https://github.com/mrfmanuel/benchtrack/issues/11)).
- **Observability is logs only:** structured JSON logs and a health check, but no metrics or traces ([#10](https://github.com/mrfmanuel/benchtrack/issues/10)), only a synthetic uptime alert ([`ops/alerting.md`](ops/alerting.md)) and no on-call automation ([#9](https://github.com/mrfmanuel/benchtrack/issues/9)).
- **No notifications:** customers aren't told by SMS, email or WhatsApp; they check the tracking page. QR codes on receipts are out of scope.
- **English UI only**, currency fixed to CRC (₡).
