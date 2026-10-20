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
