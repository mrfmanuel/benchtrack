---
name: contract-first-endpoint
description: Add or change a BenchTrack API endpoint the contract-first way — product-spec §9 decision, openapi.yaml + Redocly lint, backend tests, implementation, frontend src/api types and client, frontend tests, contract parity test, AI workflow log. Use whenever a request adds, removes or changes an /api route, request/response field, status code or error code.
argument-hint: "[what the endpoint should do]"
---

# Contract-first endpoint change

Change requested: **$ARGUMENTS**

`openapi.yaml` is the API contract and `product-spec.md` §9 wins over §1–8 (AGENTS.md). Work through the steps **in order** and don't skip one because the change "looks small": the parity tests fail if any layer is missing. Keep a checklist in your reply and tick each step as it passes.

## 1. Decide it in the spec (`product-spec.md` §9)

- Find the relevant §9 decision (validation, statuses, errors, public whitelist, pagination). If the change contradicts §1–9, **stop and ask the human**; don't silently deviate.
- If the behaviour is new, propose a §9 entry (numbered like the others) and get it confirmed before coding.
- Public routes (`/api/public/*`) must never expose PII, notes or cost (§9.13). Staff routes need the bearer token.

## 2. Contract: `openapi.yaml`

- Add or change the path, `operationId` (camelCase, unique), parameters, request body, every response (success **and** each error code from the envelope: `unauthorized`, `not_found`, `validation_error`, `conflict`, `invalid_transition`, `ticket_final`, `rate_limited`) and an example for each.
- Reuse `components/schemas` (`Error`, `Ticket`, `Page…`) instead of inline copies.
- Lint it and fix every error or warning (one rule is ignored on purpose in `.redocly.lint-ignore.yaml`):

```bash
npx --yes @redocly/cli@2.66.0 lint openapi.yaml
```

## 3. Backend tests first (`backend/tests/`)

- **Unit** (`tests/unit/`) for any new pure logic in `app/services/`.
- **API** (`tests/api/`) for each status code in the contract: happy path, 401 without token (staff routes), 404, 422 field errors (`details[].field`), 409s. Reuse `make_customer`, `make_ticket`, `move`, `assert_error` from `tests/api/conftest.py`.
- Run them and see them **fail** for the right reason:

```bash
cd backend && uv run pytest tests/api -q -k <new_test_names>
```

## 4. Implementation

- Pydantic models in `app/schemas.py` (public responses: whitelist model only).
- Business rules in `app/services/` (no HTTP, no DB session handling in routers).
- Thin route in `app/routers/` with the **same** `operation_id` as the contract.
- Model change → Alembic migration, never `create_all`:

```bash
cd backend && uv run alembic revision --autogenerate -m "<what changed>"   # review the file!
uv run alembic upgrade head
```

- Then: `uv run ruff check . && uv run ruff format --check . && uv run pytest -q`

## 5. Frontend API layer (`frontend/src/api/`)

- `types.ts`: mirror the contract exactly (field names, optionality, enums).
- `client.ts`: one method per `operationId`; all HTTP goes through `request()`. Public endpoints use `auth: false` (the token must never be sent to `/api/public/*`).
- `client.test.ts`: method, path, query params, auth header (or its absence), error envelope.

## 6. Frontend UI and tests

- Pages/components use the client only (no `fetch` in components). Show `fieldErrors` next to fields, 409s as banners.
- Pure logic goes in `src/lib/` with tests. In `beforeEach`, use braces: `beforeEach(() => { mock.mockReset(); })`.

```bash
cd frontend && npm test && npm run lint && npm run typecheck && npm run build
```

## 7. Parity checks

```bash
cd backend && uv run pytest tests/api/test_contract.py -q   # routes, operationIds, success codes, public whitelist
cd frontend && npx vitest run src/lib/statuses.test.ts       # only if the status workflow changed
```

Use the **contract-reviewer** subagent for a read-only drift report across `openapi.yaml`, the backend and `frontend/src/api` before you finish.

## 8. Log and docs

- Append a row to `docs/ai-workflow.md`: step, prompt summary, what was delegated, the Manual review cell set to `Agent self-check (human review pending): …`, and the verification with real outputs.
- Update `docs/testing.md` counts if tests were added, and `README.md`/`AGENTS.md` if commands changed.
- Commit on a feature branch (one commit per task, imperative message) and open a PR. **Never push to `main`; a human merges.**
