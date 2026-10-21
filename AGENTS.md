# AGENTS.md

Instructions for AI coding agents (and human contributors) working in this repository.

## Project

**BenchTrack** — a repair-ticket tracker for a small computer-repair shop, with a protected staff area and a public tracking page. Scope and behavior are defined in **[`product-spec.md`](product-spec.md)** (source of truth). Read it before making product or API decisions. If a request conflicts with it, flag the conflict instead of silently deviating.

**Language:** all code, comments, commit messages, docs and UI copy are in **English**.

## Repository structure

```
.
├── product-spec.md        # Product spec — source of truth for scope/behavior
├── openapi.yaml           # API contract — source of truth for the API
├── AGENTS.md / CLAUDE.md  # Agent instructions (CLAUDE.md just points here)
├── backend/               # FastAPI + SQLAlchemy (Python, uv)
├── frontend/              # Vite + React + TypeScript SPA
├── docker-compose.yml     # postgres + app (local full stack)
├── Dockerfile             # multi-stage: builds frontend, serves it from FastAPI
├── docker/                # container entrypoint (migrate + uvicorn) and health check
├── .github/workflows/     # CI (tests, scans) and CD (deploy on main)
├── docs/                  # architecture, AI workflow log, deployment, testing
├── security/              # scan outputs, PR audit, agent security notes, AI policy
├── ops/                   # runbook, health checks, incident diagnosis
├── agent-capabilities/    # skills + subagents (Module 5)
├── agent-hooks/           # hook scripts / guardrails (Module 5)
├── mcp-server/            # read-only MCP server over the BenchTrack API (Module 5)
└── plugins/               # Claude Code plugin bundling the pack (Module 5)
```

## Golden rules

1. **Contract first.** Any API change starts in `openapi.yaml`, then backend, then `frontend/src/api/`, then tests — in the same change.
2. **Tests with every change.** Backend tests live in three layers (see *Backend tests* below); frontend tests next to the code (`*.test.ts(x)`). Don't mark work done while tests fail.
3. **Small steps, one commit per task**, message in imperative mood (`Add status transition validation`).
4. **No secrets in the repo.** Use `.env` (git-ignored) and `.env.example`. Never print or commit `STAFF_TOKEN`, `DATABASE_URL` or deploy hooks.
5. **Fictional data only** in seeds, tests and screenshots.
6. **Log AI usage**: after each significant task, append a short entry to `docs/ai-workflow.md` (prompt summary, what was delegated, what was reviewed manually, how it was verified).

## Backend (`backend/`)

- FastAPI, Python 3.12, managed with **uv** (`uv add`, `uv sync`, `uv run ...`; never `pip install`, never hand-edit `uv.lock`).
- Layout: `app/main.py` (app factory), `app/config.py` (settings from env), `app/db.py` (engine/session), `app/models.py` (SQLAlchemy), `app/schemas.py` (Pydantic), `app/services/` (business logic, e.g. status transitions, tracking codes), `app/routers/` (thin HTTP layer).
- Business rules (transitions, tracking code generation, stale detection) live in `app/services/` and are unit-tested without HTTP or DB.
- DB: SQLAlchemy 2.x, engine-agnostic models. `DATABASE_URL` defaults to SQLite (`sqlite:///./benchtrack.db`); PostgreSQL in Compose/production. Keep engine-specific code in `app/db.py`. Details: [`docs/database.md`](docs/database.md).
- Schema changes **only via Alembic** (`backend/alembic/`): change `app/models.py`, run `uv run alembic revision --autogenerate -m "..."`, review the file, then `uv run alembic upgrade head`. The app never calls `create_all` (only the API test fixture does). Never edit an applied migration.
- Auth: `Authorization: Bearer <STAFF_TOKEN>` dependency on all staff routes; compare with `secrets.compare_digest`.
- Run: `uv run alembic upgrade head` then `uv run uvicorn app.main:app --reload` · Lint: `uv run ruff check .` · Seed: `uv run python -m app.seed`
- Local PostgreSQL: `docker compose up -d db --wait` (127.0.0.1:5433; use `127.0.0.1`, not `localhost`).
- API docs: `GET /docs` (Swagger UI) renders the served contract `GET /api/openapi.yaml`; FastAPI's generated schema is disabled.

### Backend tests

| Layer | Folder | Scope | Run |
|-------|--------|-------|-----|
| Unit | `backend/tests/unit/` | Pure logic in `app/services/` and config — no HTTP, no DB. Fast. | `uv run pytest tests/unit` |
| API | `backend/tests/api/` | In-process HTTP via `TestClient` + in-memory SQLite (`StaticPool`), settings overridden. Acceptance scenarios, error codes, auth, contract parity with `openapi.yaml`. | `uv run pytest tests/api` |
| Integration | `backend/tests/integration/` | Compose PostgreSQL via `TEST_DATABASE_URL` (database name must end in `_test`; schema is wiped per test). Migrations up/down, no autogenerate drift, key HTTP workflows. Marker `integration`; skipped without PostgreSQL. | `uv run pytest -m integration` |

`uv run pytest` runs unit + API tests (integration is deselected by default).

## Frontend (`frontend/`)

- Vite + React 19 + TypeScript, react-router, plain CSS (`src/index.css`). **All HTTP calls go through `src/api/client.ts`** — no `fetch` in components. The client attaches the bearer token (never on `/api/public/*`), parses the error envelope into `ApiError` (`status`, `code`, `message`, `details`, `fieldErrors`, `retryAfter`), and on any `401` clears the stored token and redirects to sign-in.
- Types for API payloads live in `src/api/types.ts` and must match `openapi.yaml`.
- Pure logic (status labels/colors, allowed next statuses, money/date formatting, tracking-code normalization, form helpers) in `src/lib/` with Vitest tests. `src/lib/statuses.test.ts` parses the transition table out of `product-spec.md` and `openapi.yaml`, so a workflow change must update both docs and `statuses.ts`.
- Layout: `src/pages/` (one per route), `src/components/`, `src/layouts/` (staff vs. minimal public layout), `src/hooks/useApi.ts`.
- API base URL: relative `/api` (same origin in production). The Vite dev server proxies `/api` and `/docs` to `http://127.0.0.1:8000` (`127.0.0.1`, not `localhost`: see the Windows note in `docs/database.md`); override with the shell variable `API_PROXY_TARGET`.
- Build-time config: `VITE_SHOP_NAME` (receipt and header), see `frontend/.env.example`. `VITE_*` values are public — never put secrets there.
- Run (from `frontend/`): `npm install` once, then `npm run dev` (http://localhost:5173) · Tests: `npm test` · Lint: `npm run lint` (oxlint) · Type-check: `npm run typecheck` · Build: `npm run build`.
- In tests, write `beforeEach(() => { mock.mockReset(); })` with braces: Vitest runs a function returned from `beforeEach` as teardown.

## Running everything

- Full stack: `docker compose up --build -d --wait` → app on http://localhost:${APP_PORT:-8000}; seed with `docker compose exec app python -m app.seed`. Logs: `docker compose logs app` (JSON).
- The image mirrors the repo layout under `/app` (`/app/backend`, `/app/openapi.yaml`, `/app/frontend/dist`); the build fails if the contract or `index.html` is not where the app reads it. `docker/entrypoint.sh` runs `alembic upgrade head`, then uvicorn on `$PORT` with proxy headers. It runs as the non-root user `benchtrack`.
- SPA serving (`app/spa.py`, enabled by `FRONTEND_DIST`) is a 404 fallback: GET requests for unknown non-`/api`, non-`/assets` paths get `index.html`; `/api/*` keeps the JSON error envelope. Add API routes under `/api` only.
- Shell scripts and the Dockerfile must stay LF (`.gitattributes`).
- CI must stay green; CD deploys only after all tests pass on `main`.

## Don'ts

- Don't add features listed as out of scope in `product-spec.md`.
- Don't expose customer PII or internal notes on `/api/public/*`.
- Don't disable tests, linters or scanners to make CI pass — fix the cause or document the exception in `security/`.
- Don't run destructive commands (`rm -rf`, `DROP`, `git push --force`, `docker system prune`) without asking.
