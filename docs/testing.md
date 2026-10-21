# Testing

How BenchTrack is tested, from fast pure-logic tests to the containerized app. Every layer runs in CI ([`.github/workflows/ci.yml`](../.github/workflows/ci.yml)); the counts below are as of 2026-10-21 — update them when you add tests.

## Test pyramid

```
                 ┌───────────────────────────────┐
                 │ Docker smoke test (CI only)   │  image + PostgreSQL, curl /api/health, /, /api/nope
                 ├───────────────────────────────┤
                 │ Integration — 10              │  real PostgreSQL, Alembic, key HTTP workflows
             ┌───┴───────────────────────────────┴───┐
             │ API — 264 (incl. contract parity, SPA, headers) │  in-process HTTP, in-memory SQLite
         ┌───┴───────────────────────────────────────┴───┐
         │ Unit — 285 backend · Vitest — 136 frontend     │  pure logic, no HTTP or DB
         └───────────────────────────────────────────────┘
  Static checks: Redocly (contract) · ruff · oxlint · tsc · Semgrep · actionlint
```

## Run everything with one command

From the repo root, on Windows PowerShell, Linux or macOS (needs uv, Node.js and Docker):

```bash
uv run --no-project python scripts/test_all.py
```

[`scripts/test_all.py`](../scripts/test_all.py) starts the Compose PostgreSQL, then runs the backend unit, API and integration tests in **one** pytest run (559), Vitest (136), the hook tests, the sync-script tests and drift check, and the MCP server tests. It prints a PASS/FAIL summary and exits non-zero on any failure. With `--skip-integration` it needs no Docker. It uses `TEST_DATABASE_URL` if set, else the Compose default `…@127.0.0.1:<DB_PORT>/benchtrack_test` (`DB_PORT` from the shell or `.env`, default 5433). The sections below run each layer on its own.

| Layer | Where | Tests | Command | Needs |
|---|---|---:|---|---|
| Backend unit | `backend/tests/unit/` | 285 | `uv run pytest tests/unit` | nothing |
| Backend API | `backend/tests/api/` | 264 | `uv run pytest tests/api` | nothing |
| Backend default run (unit + API) | both of the above | 549 | `uv run pytest` | nothing |
| Backend integration | `backend/tests/integration/` | 10 | `uv run pytest -m integration` | PostgreSQL + `TEST_DATABASE_URL` |
| Contract parity | `backend/tests/api/test_contract.py` | 4 | `uv run pytest tests/api/test_contract.py` | nothing |
| Contract lint | `openapi.yaml` | — | `npx @redocly/cli@2.66.0 lint openapi.yaml` | Node |
| Frontend | `frontend/src/**/*.test.ts(x)` | 136 in 11 files | `npm test` | Node |
| Agent hooks (guard, ruff hook) | `agent-hooks/tests/` | 35 (plus sub-cases) | `python -m unittest discover -s agent-hooks/tests` | Python 3.12 (stdlib) |
| MCP server | `mcp-server/tests/` | 25 | `cd mcp-server && uv run pytest -q` | nothing (mocked API) |
| Agent pack sync (plugin and `.claude/` copies) | `plugins/tests/` | 9 | `python -m unittest discover -s plugins/tests`, then `python plugins/sync_plugin.py --check` | nothing |
| Repo scripts (`test_all.py` helpers, uptime check) | `scripts/tests/` | 25 | `python -m unittest discover -s scripts/tests` | nothing (fake HTTP and `gh`) |
| Docker smoke | `ci.yml` job `docker` | — | see [below](#docker-image) | Docker |

Backend commands run from `backend/`, frontend commands from `frontend/`, Redocly from the repo root.

## Backend (`backend/`)

### Unit — `tests/unit/` (282)

Pure functions in `app/services/` and `app/config.py`, no HTTP and no database: status transitions (the full allowed/forbidden matrix), tracking-code generation and normalization, phone normalization, stale detection, the sliding-window rate limiter, log masking of tracking codes, rate-limit client keys (never `X-Forwarded-For`, IPv6 by /64), CSP construction and HTTPS detection, settings validation (`STAFF_TOKEN` length, URL normalization, `version` precedence: `APP_VERSION` → `RENDER_GIT_COMMIT` → `dev`) and engine options. They run in about a second.

```powershell
cd backend
uv run pytest tests/unit
```

### API — `tests/api/` (255)

In-process HTTP through FastAPI's `TestClient` against in-memory SQLite (`StaticPool`), with settings, the clock and the log stream injected by `tests/api/conftest.py`. They cover the acceptance scenarios from the spec, every error code and envelope, auth on each staff route, the public whitelist, rate limiting with a fake clock, JSON logging with masked codes, the UTF-8 charset, `/docs` and `/api/openapi.yaml`, the seed script, security headers on every response kind including 401/404/405/422/429/500 (`test_security_headers.py`), and SPA serving (`test_spa.py`: `index.html` fallback, `/api/*` keeps the JSON 404, no files outside `dist/`).

```powershell
uv run pytest tests/api
uv run pytest          # unit + API (integration is deselected in pyproject.toml): 549 passed, 10 deselected
```

### Contract parity — `tests/api/test_contract.py` (4)

Loads `openapi.yaml` and compares it with the routes FastAPI actually registers: every contract operation exists in the app and vice versa (only `/docs` and `/api/openapi.yaml` are exempt), operation IDs and success status codes match, and the public tracking schema matches the whitelist model, so no PII field can slip into `/api/public/*`. A change to the contract without the code (or the reverse) fails here.

### Integration — `tests/integration/` (10)

Real PostgreSQL: `alembic upgrade head` on an empty database, constraint naming, **no autogenerate drift** between models and migrations, downgrade to base and upgrade again, and the key HTTP workflows (full ticket lifecycle with timeline, invalid transition 409, public whitelist, duplicate phone 409, stale detection, case-insensitive search). Marked `integration`, so the default run skips them.

1. Start the Compose PostgreSQL (published on `127.0.0.1:5433`, or `DB_PORT` if set):

   ```powershell
   docker compose up -d db --wait
   ```

2. Point the tests at a database whose name ends in `_test`. **Its schema is dropped and recreated for every test**; the fixtures refuse other names and create the database if it is missing.

   ```powershell
   $env:TEST_DATABASE_URL = "postgresql+psycopg://benchtrack:benchtrack@127.0.0.1:5433/benchtrack_test"
   uv run pytest -m integration          # 10 passed, 549 deselected
   ```

   Use `127.0.0.1`, not `localhost` (see the Windows note in [`database.md`](database.md)), and your `DB_PORT` instead of `5433` if you changed it. `TEST_DATABASE_URL` can also live in `.env`.

Without `TEST_DATABASE_URL` the integration tests are **skipped**, not failed. CI therefore fails the `integration` job if any test is skipped.

### Lint

```powershell
uv run ruff check .
uv run ruff format --check .
```

## Frontend (`frontend/`) — Vitest (136 in 11 files)

Vitest + Testing Library + jsdom (`src/test/setup.ts` cleans up the DOM and `localStorage` after each test).

| Area | Files | What they pin down |
|---|---|---|
| `src/lib/` | `statuses`, `format`, `trackingCode`, `forms`, `ticketForm`, `errors`, `tokenStore` | labels and colors, allowed next statuses, ₡ and date formatting, code normalization, form/validation helpers |
| API client | `src/api/client.test.ts` | bearer header (never on `/api/public/*`), query params, error-envelope parsing into `ApiError`, `Retry-After`, network errors, 401 clears the token and redirects |
| Components / pages | `StatusChangeControl`, `TrackPage`, `SignInPage` | only allowed statuses offered, none when final; public page timeline, progress, 404 and 429 messages; token validation on sign-in |

`src/lib/statuses.test.ts` parses the transition table out of `product-spec.md` and `openapi.yaml` and compares it with `statuses.ts`, so the frontend cannot drift from the documented workflow.

```powershell
cd frontend
npm ci
npm test               # Test Files 11 passed (11) · Tests 136 passed (136)
npm run lint           # oxlint
npm run typecheck      # tsc -b
npm run build          # type-check + production build
```

## Contract lint — Redocly

```powershell
npx --yes @redocly/cli@2.66.0 lint openapi.yaml
```

Expected: `Your API description is valid` with `1 problem is explicitly ignored` — `GET /api/health` has no 4XX response by design, documented in [`.redocly.lint-ignore.yaml`](../.redocly.lint-ignore.yaml). Redocly also validates every example in the contract against its schema.

## Docker image

The CI `docker` job builds the root `Dockerfile` with `APP_VERSION=<commit SHA>`, runs it with `--network host` against a `postgres:16` service, and checks: `/api/health` reports `ok` and that commit as `version`, `/` and `/track/BT-AAAAA` return the SPA, `/api/nope` is a JSON 404, `/docs` and `/api/openapi.yaml` respond, and the image runs as the `benchtrack` user. Locally, the equivalent is the Compose quick start in the [README](../README.md#quick-start-docker-compose):

```powershell
docker compose up --build -d --wait
curl.exe -s http://127.0.0.1:8000/api/health
```

## Security and workflow checks

Dependency, secret and code scans with triage: [`security/scan-findings.md`](../security/scan-findings.md) (raw outputs in `security/scans/`).

```powershell
# Semgrep (same as CI; --error fails on any finding)
docker run --rm -v "${PWD}:/src" -w /src semgrep/semgrep:1.182.0 semgrep scan --config auto --error
# actionlint for .github/workflows/
docker run --rm -v "${PWD}:/repo" -w /repo rhysd/actionlint:1.7.12
```

## CI mapping

| `ci.yml` job | Runs |
|---|---|
| `contract` | Redocly lint |
| `backend` | `uv sync --locked`, ruff check + format check, `uv run pytest` (unit + API) |
| `integration` | `postgres:16` service, `TEST_DATABASE_URL`, `uv run pytest -m integration` (fails on skips) |
| `frontend` | Node 24, `npm ci`, lint, test, build |
| `docker` | image build (GitHub Actions cache) + smoke test against PostgreSQL |
| `agent-pack` | guard + ruff hook unit tests, JSON validity of agent configs, sync script and repo script tests, plugin and `.claude/` copies in sync, MCP server ruff + tests |
| `semgrep` | `semgrep scan --config auto --error`; SARIF and JSON uploaded as the `semgrep-results` artifact |

`cd.yml` deploys only after a successful CI run for a push to `main`, then polls `/api/health` (up to ~10 minutes) until `status` is `ok` and `version` equals the commit CI tested.
