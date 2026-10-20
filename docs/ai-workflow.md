# AI Workflow

This project is built with **Claude Code** as the AI coding assistant. This file records how AI was used: what was delegated, what was reviewed by a human, and how each step was verified.

## Context files

The agent is grounded with these files, which are kept in the repository:

- [`AGENTS.md`](../AGENTS.md) — project instructions for all coding agents (structure, golden rules, commands)
- [`CLAUDE.md`](../CLAUDE.md) — Claude Code entry point; points to `AGENTS.md`
- [`product-spec.md`](../product-spec.md) — product scope and behavior (source of truth)
- [`openapi.yaml`](../openapi.yaml) — API contract (source of truth for the API)

## Workflow

**spec → contract → tests → code → review → verify**

1. **Spec** — clarify scope in `product-spec.md`.
2. **Contract** — define or change the API in `openapi.yaml` first.
3. **Tests** — write unit/integration tests that encode the spec and contract.
4. **Code** — implement until tests pass.
5. **Review** — human review of the diff (correctness, security, scope).
6. **Verify** — run tests, linters and the app; record the evidence below.

## Log

| Step | Prompt (summary) | Delegated to AI | Manual review | Verification |
|------|------------------|-----------------|---------------|--------------|
| 0 — Skeleton | Read `AGENTS.md` and `product-spec.md`; create `.gitignore`, `.env.example`, placeholder `README.md` and this log; no app code. | Drafting all four files; listing spec gaps. | Checked ignore rules cover Python/Node/`.env`/`*.db`/IDE files and that `.env.example` holds no real secrets. | `git status` / `git check-ignore -v` confirm `.env.example` is tracked and secrets/DB files are ignored. |
| 1 — Spec review | Agent reviewed the spec and raised 27 questions/gaps (validation, workflow, tracking codes, security, API shape, ops). | Identifying ambiguities and their impact on the API contract. | Human answered all 27 in `product-spec.md` §9 "Clarifications and decisions". Agent then added `LOG_FORMAT` and the 16-char token note to `.env.example` and aligned `README.md` with the spec. | Agent re-read §9 and cross-checked `.env.example` and `README.md` against it. |
| 2 — API contract | Write `openapi.yaml` (OpenAPI 3.1) from the spec (§9 wins): health, customers, tickets, status, notes, events, dashboard, public tracking; bearer auth globally, none on health/public; shared schemas with spec limits; single `Error` envelope; fictional examples; lint with Redocly. | Drafting the full contract (14 operations, reusable schemas/parameters/responses, examples) and fixing lint findings. | Human reviewed openapi.yaml: confirmed the public tracking schema is a closed whitelist (7 fields, timeline = status + timestamp only, no PII/notes/cost/serial); TicketUpdate rejects customer_id/status/tracking_code; security is global with overrides only on health and public; accepted the health 503 deviation (spec §9.22 wins over the prompt); requested a customer_id filter on ticket listing and 422 instead of 404 for an unknown customer on ticket creation. | `npx @redocly/cli lint openapi.yaml` → valid, 0 errors, 0 warnings; 1 ignored (`operation-4xx-response` on health, reason in `.redocly.lint-ignore.yaml`). Redocly also validates every example against its schema. |
| 2a — Backend core (test-first) | Add `.gitattributes` (LF, CRLF for `*.ps1`, binaries) as a separate commit. Scaffold `backend/` with uv (Python 3.12, FastAPI, SQLAlchemy 2, pydantic-settings, psycopg, pytest, httpx, ruff); `app/config.py`; unit tests first for `transitions`, `tracking_codes`, `staleness`, `phone`, `log_masking`, then implement. | Scaffolding, writing 212 unit tests (incl. `test_config.py`), stub modules for the red run, the five services and settings. | Human reviewed the services and tests: verified the transition test encodes the spec table independently of the implementation (49 pairs, 13 allowed, final statuses without exits); tracking code alphabet/format and the try_create collision design; strict code normalization (BT7K3QX rejected); config fails fast on short STAFF_TOKEN and normalizes postgres:// URLs; no pycache committed. Accepted all 5 agent choices. | Red: stubs raising `NotImplementedError` → 198 failed / 14 passed (trivial passes: empty alphabet, stub `Settings`, test-data checks). Green: `uv run pytest tests/unit -q` → 212 passed; `uv run ruff check .` → all checks passed. |
| 2b — HTTP API | Add uvicorn; settings read `../.env` and `.env`. Implement `db.py`, `models.py`, `schemas.py`, thin routers + service functions strictly per `openapi.yaml`; error envelope handlers; bearer auth; in-memory sliding-window rate limiter; logging with masking (incl. uvicorn access logs); health; `create_all`; idempotent fictional seed. API tests in `tests/api/` incl. acceptance scenarios, every error code, public whitelist, rate limit, log masking, contract parity. | Implementation of all modules, seed, 194 API tests + 6 rate-limiter unit tests; contract update adding the `ticket_final` example to the status endpoint's 409. | Agent self-check (human review pending): contract parity also checks operationIds and success codes; parity test verified to fail when an extra route is added (FastAPI 0.156 nests included routers, so routes are walked via `iter_route_contexts`); raw public lookups are never logged because un-prefixed codes can't be masked; found and fixed `STAFF_TOKEN` being echoed in the startup ValidationError (`hide_input_in_errors`); `updated_at` tests backdate first because the Windows clock on Python 3.12 can tick only every ~15 ms. | `uv run ruff check .` → all passed; `uv run pytest` → 412 passed (218 unit, 194 API). Live: seeded SQLite twice (6+12, then 0+0), `uvicorn app.main:app` → `curl.exe /api/health` = `200 {"status":"ok","database":"ok"}`; 401 without token; dashboard shows all 7 counts and 3 stale; public lookup `dem24` works and the uvicorn access log shows `/api/public/track/BT-*****`; `STAFF_TOKEN=change-me` stops startup without echoing the value. |
