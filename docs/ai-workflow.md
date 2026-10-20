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
| 2a — Backend core (test-first) | Add `.gitattributes` (LF, CRLF for `*.ps1`, binaries) as a separate commit. Scaffold `backend/` with uv (Python 3.12, FastAPI, SQLAlchemy 2, pydantic-settings, psycopg, pytest, httpx, ruff); `app/config.py`; unit tests first for `transitions`, `tracking_codes`, `staleness`, `phone`, `log_masking`, then implement. | Scaffolding, writing 212 unit tests (incl. `test_config.py`), stub modules for the red run, the five services and settings. | Agent self-check (human review pending): tests hard-code the spec tables instead of importing them; all 49 status pairs parametrized; phone regex uses ASCII `[0-9]` (Python `\d` would accept full-width digits); masking covers un-prefixed codes in `/track/` paths. Ruff `S105` allowed only under `tests/**` for fictional tokens. | Red: stubs raising `NotImplementedError` → 198 failed / 14 passed (trivial passes: empty alphabet, stub `Settings`, test-data checks). Green: `uv run pytest tests/unit -q` → 212 passed; `uv run ruff check .` → all checks passed. |
