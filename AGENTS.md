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
- DB: SQLAlchemy 2.x, engine-agnostic models. `DATABASE_URL` defaults to SQLite (`sqlite:///./benchtrack.db`); PostgreSQL in Compose/production. Keep engine-specific code in `app/db.py`.
- Auth: `Authorization: Bearer <STAFF_TOKEN>` dependency on all staff routes; compare with `secrets.compare_digest`.
- Run: `uv run uvicorn app.main:app --reload` · Lint: `uv run ruff check .` · Seed: `uv run python -m app.seed`
- API docs: `GET /docs` (Swagger UI) renders the served contract `GET /api/openapi.yaml`; FastAPI's generated schema is disabled.

### Backend tests

| Layer | Folder | Scope | Run |
|-------|--------|-------|-----|
| Unit | `backend/tests/unit/` | Pure logic in `app/services/` and config — no HTTP, no DB. Fast. | `uv run pytest tests/unit` |
| API | `backend/tests/api/` | In-process HTTP via `TestClient` + in-memory SQLite (`StaticPool`), settings overridden. Acceptance scenarios, error codes, auth, contract parity with `openapi.yaml`. | `uv run pytest tests/api` |
| Integration | `backend/tests/integration/` | Real PostgreSQL with Alembic migrations (Step 3). | `uv run pytest tests/integration` |

`uv run pytest` runs all layers.

## Frontend (`frontend/`)

- Vite + React + TypeScript. **All HTTP calls go through `src/api/client.ts`** — no `fetch` in components.
- Types for API payloads live in `src/api/types.ts` and must match `openapi.yaml`.
- Pure logic (status labels/colors, allowed next statuses, date formatting) in `src/lib/` with Vitest tests.
- API base URL: relative `/api` (same origin in production; Vite dev proxy to `http://localhost:8000` locally).
- Run: `npm run dev` · Tests: `npm test` · Build: `npm run build`.

## Running everything

- Full stack: `docker compose up --build` → app on http://localhost:8000.
- CI must stay green; CD deploys only after all tests pass on `main`.

## Don'ts

- Don't add features listed as out of scope in `product-spec.md`.
- Don't expose customer PII or internal notes on `/api/public/*`.
- Don't disable tests, linters or scanners to make CI pass — fix the cause or document the exception in `security/`.
- Don't run destructive commands (`rm -rf`, `DROP`, `git push --force`, `docker system prune`) without asking.
