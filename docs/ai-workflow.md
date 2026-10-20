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
