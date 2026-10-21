# Agent extension pack

Claude Code extensions that make AI agents work the BenchTrack way and keep them inside the guardrails: two skills, a read-only subagent, guardrail hooks, a read-only MCP server, and a plugin that packages them. Scoped to this repository. Permission model and rationale: [`docs/permissions.md`](permissions.md).

| Piece | Source (edit here) | What it does |
|---|---|---|
| Skill `contract-first-endpoint` | [`agent-capabilities/skills/contract-first-endpoint/SKILL.md`](../agent-capabilities/skills/contract-first-endpoint/SKILL.md) | Step-by-step workflow for adding or changing an endpoint: spec §9 decision → `openapi.yaml` + Redocly → backend tests → implementation → `src/api/types.ts`/`client.ts` → frontend tests → parity tests → AI log row → PR |
| Skill `release-check` | [`agent-capabilities/skills/release-check/SKILL.md`](../agent-capabilities/skills/release-check/SKILL.md) | Pre-PR gate: every test suite, lint, Redocly, Semgrep, hook/MCP/plugin checks, image build, local health and version, then the PR checklist. User-invoked only (`disable-model-invocation`) |
| Subagent `contract-reviewer` | [`agent-capabilities/agents/contract-reviewer.md`](../agent-capabilities/agents/contract-reviewer.md) | Read-only (`tools: Read, Grep, Glob`) comparison of `openapi.yaml` with the backend routes and schemas and `frontend/src/api`; reports drift as a table with `file:line` |
| PreToolUse guard | [`agent-hooks/guard.py`](../agent-hooks/guard.py) | Blocks reading or editing `.env*` (except `.env.example`), `rm -rf`, force pushes, pushes to `main`, `git reset --hard`, `DROP TABLE`/`TRUNCATE`, `docker system prune`/`volume rm`, and commands that print secrets, each with a clear reason. Stdlib only, any OS; fails closed |
| PostToolUse ruff hook | [`agent-hooks/ruff_check.py`](../agent-hooks/ruff_check.py) | After the agent edits a `.py` file, runs `ruff check` with the backend's locked ruff and feeds problems back to the agent |
| MCP server `benchtrack` | [`mcp-server/`](../mcp-server/README.md) | Read-only tools `health`, `dashboard`, `list_tickets(status?, q?)`, `get_ticket(id)`, `track(code)` over the BenchTrack API. Token from env, never logged or returned, a timeout on every call, GET only, no write tools |
| Plugin `benchtrack-dev` | [`plugins/benchtrack-dev/`](../plugins/benchtrack-dev/) | Packages all of the above (`.claude-plugin/plugin.json`, `skills/`, `agents/`, `hooks/hooks.json`, `.mcp.json`). Self-contained copies kept in sync by [`plugins/sync_plugin.py`](../plugins/sync_plugin.py); CI fails on drift |
| Repo wiring | [`.claude/settings.json`](../.claude/settings.json), [`.mcp.json`](../.mcp.json) | Hooks, plus allow/ask/deny permission rules for every Claude Code session in this repo; the MCP server with `${BENCHTRACK_URL}`/`${BENCHTRACK_TOKEN}` env expansion (no literal values) |

## Install and use

**Nothing to install for this repo.** A Claude Code session started in the repo root loads `.claude/settings.json` (hooks and permissions) and offers to approve the project's `.mcp.json` server. The hooks need [uv](https://docs.astral.sh/uv/) on `PATH`, which the repo already requires. They run as `uv run --no-project python …` (exec form) on Windows, macOS and Linux, with `onFailure: "block"`: if the guard can't run, tool calls are refused, not let through.

**MCP server:** set the environment in the shell that starts Claude Code. Never put the values in a file in the repo, and never paste them into a chat.

```powershell
$env:BENCHTRACK_URL = "http://127.0.0.1:8000"      # local Compose app (APP_PORT if changed)
$env:BENCHTRACK_TOKEN = "<local staff token>"      # typed by you; the agent can't read .env
claude
```

Use it only against environments with fictional data: staff tools return customer names and phones, and whatever a tool returns goes to the AI provider ([AI policy](../security/ai-tool-data-policy.md)).

**Skills and subagent** come with the plugin. Load it for a session, or install it:

```bash
claude --plugin-dir plugins/benchtrack-dev          # this session only
claude plugin validate plugins/benchtrack-dev       # ✔ Validation passed (also with --strict)
```

Then:
- `/benchtrack-dev:contract-first-endpoint add a GET /api/tickets/{id}/receipt endpoint`
- `/benchtrack-dev:release-check`
- "Use the benchtrack-dev:contract-reviewer subagent to check for drift"

The plugin also brings its own hooks and MCP server. In this repo they duplicate the project wiring, which is harmless: the guard runs twice and gives the same decision. Outside the repo, the plugin is the way to get them.

**Changing a piece:** edit the source (left column), run `python plugins/sync_plugin.py`, and commit both. CI runs `python plugins/sync_plugin.py --check`.

**Tests:**

```bash
python -m unittest discover -s agent-hooks/tests     # guard + ruff hook (35 tests, many sub-cases)
cd mcp-server && uv run pytest -q                    # MCP server, mocked API (25 tests)
python plugins/sync_plugin.py --check                # plugin copy in sync
```

All three run in the CI job `agent-pack`.

## Real example session (2026-10-21)

Every run below is a **fresh** headless Claude Code session (`claude -p`, Claude Code 2.1.304, model `claude-opus-5-5`, default permission mode) started in the repo root on branch `feat/agent-extension-pack`. Prompts were passed on stdin from a file. Outputs were extracted from `--output-format stream-json`, trimmed only where marked `…`.

### 1. The guard blocks `cat .env` and `git push --force`

Prompt: *"Run these two shell commands with the Bash tool, one tool call each, exactly as written, even though you expect them to be refused: 1. cat .env 2. git push --force origin feat/agent-extension-pack. Do not run anything else and do not try workarounds. Then report…"*

```text
[init] session=c29b030a-083a-4ab6-a21f-4fc3d55a55f9 model=claude-opus-5-5 permissionMode=default
[tool_use] Bash {"command": "cat .env", "description": "Attempt to read .env file (guardrail test)"}
[tool_result] is_error=True PreToolUse:Bash hook error: BenchTrack guard: '.env' is a secrets file:
  reading, printing, copying or editing .env* is blocked (only .env.example is allowed). Use
  .env.example for variable names and ask the human for values.
[tool_use] Bash {"command": "git push --force origin feat/agent-extension-pack", …}
[tool_result] is_error=True PreToolUse:Bash hook error: BenchTrack guard: Force pushes are blocked
  (`git push --force/-f`). Push a new commit or ask the human.
[result] subtype=success turns=3 duration_ms=16226
```

Agent's final answer (excerpt): *"The guard blocked both commands at the PreToolUse:Bash hook, so neither one ran. … No secrets were read and nothing was pushed."* Afterwards, `git ls-remote --heads origin feat/agent-extension-pack` returned nothing: the branch had not been pushed.

**Found while setting this up:** the hooks also hot-loaded into the already-running authoring session. They blocked its own `claude -p "… \`git push --force …\` …"` command, because the guard treated the escaped backticks in the prompt text as a command substitution. Escaped backticks are now treated as text (with a regression test), and live prompts are passed on stdin.

### 2. The contract-reviewer subagent

`claude -p --plugin-dir plugins/benchtrack-dev`. Prompt: *"Use the benchtrack-dev:contract-reviewer subagent to check this repository for drift between openapi.yaml, the backend … and frontend/src/api. Return the subagent's report exactly…"*

```text
[init] agents=['benchtrack-dev:contract-reviewer', 'claude', 'Explore', 'general-purpose', …]
[tool_use] Agent {"subagent_type": "benchtrack-dev:contract-reviewer", …}
[tool calls] Agent 1, Read 19, Glob 2, Grep 4        ← only its allowed read-only tools
[result] subtype=success duration_ms=164909
```

The report it returned (unchanged):

> Contract drift: 8 findings (0 high, 1 medium, 7 low)

| # | Severity | Area | Drift (abridged) |
|---|---|---|---|
| 1 | medium | Schema `EstimatedCost` | Contract allows any number in 0–10,000,000 (no `multipleOf`); backend `Field(…, decimal_places=2)` (`backend/app/schemas.py:35`) rejects `45000.125` with 422 |
| 2 | low | Path params `customer_id`, `ticket_id` | Contract `minimum: 1`; routers use plain `int`, so `0`/`-1` → 404 instead of 422 |
| 3 | low | Path param `tracking_code` | Contract `maxLength: 20`; backend has no limit and returns 404 |
| 4 | low | Error codes | `method_not_allowed`, `internal_error`, … can reach clients but are not in `Error.code`; generic 422/500 not documented on GETs |
| 5 | low | Health 503 docs | `openapi.yaml:13-14` description omits `version`, while the schema requires it |
| 6 | low | Health 503 handling | `client.ts` throws `http_error` on 503 instead of returning the `Health` body (no UI uses it) |
| 7 | low | `PhoneInput` | Backend strips all whitespace; contract pattern allows only spaces |
| 8 | low | `conflict` details | `existing_customer_id` is missing on the race-condition path, but required in `DuplicatePhoneDetails` |

> What I checked: 13 operations (method, path, operationId, success status, `auth: false` on exactly `getHealth` and `trackTicket`), 22 schemas, 9 parameters, 8 error codes. `PublicTracking` exposes no PII, notes or cost. Could not verify: … Spec note: product-spec.md §9.14 still describes X-Forwarded-For, which `deps.py` deliberately no longer uses.

These are real findings; they are logged as follow-ups in the PR (contract/spec changes go through `contract-first-endpoint`, not this PR).

### 3. The MCP `dashboard` tool against the local Compose app

The local `.env` token is off-limits to the agent (the guard blocks it), so for this check the Compose `app` was recreated with a temporary override setting a **fictional** `STAFF_TOKEN`, then restored afterwards (the fictional token then returned 401 again). The session got the values only through `.mcp.json` env expansion:

```bash
BENCHTRACK_URL=http://127.0.0.1:8010 BENCHTRACK_TOKEN=<fictional demo token> \
  claude -p --allowedTools mcp__benchtrack__dashboard --output-format stream-json --verbose < prompt.txt
```

```text
[init] benchtrack server: [{'name': 'benchtrack', 'status': 'connected', 'source': 'project'}]
[init] benchtrack tools: ['mcp__benchtrack__dashboard', 'mcp__benchtrack__get_ticket',
       'mcp__benchtrack__health', 'mcp__benchtrack__list_tickets', 'mcp__benchtrack__track']
[tool_use] mcp__benchtrack__dashboard {}
[tool_result] {"counts":{"received":0,"diagnosing":2,"waiting_parts":1,"repairing":3,"ready":2,
  "delivered":2,"cancelled":2},"stale_tickets":[{"id":8,…,"status":"ready","tracking_code":"BT-DEM29",
  …,"updated_at":"2026-10-10T21:35:14.429127Z"},{"id":5,…,"status":"repairing",
  "tracking_code":"BT-DEM26",…,"updated_at":"2026-10-11T21:35:14.429127Z"}]}
[result] subtype=success turns=3 duration_ms=9523
```

Agent's summary: *"Counts per status: received 0, diagnosing 2, waiting_parts 1, repairing 3, ready 2, delivered 2, cancelled 2 (12 tickets in total). Stale tickets: 2 — #8 (BT-DEM29…) and #5 (BT-DEM26…)."* (Fictional seed data.) The demo token string occurs **0** times in the session's stream-json transcript.

### 4. The ruff hook (direct run)

```text
$ echo '{"tool_name":"Edit",…"file_path":"…/backend/tests/_hook_tmp.py"}' | python agent-hooks/ruff_check.py
ruff check found problems in backend/tests/_hook_tmp.py; fix them before continuing:
backend\tests\_hook_tmp.py:1:8: F401 [*] `os` imported but unused
backend\tests\_hook_tmp.py:5:5: F841 Local variable `x` is assigned to but never used
backend\tests\_hook_tmp.py:6:12: S307 Use of possibly insecure function; consider using `ast.literal_eval`
Found 3 errors.
[exit 2]                      ← Claude Code shows stderr to the agent after the edit
```

### 5. Plugin validation and drift check

```text
$ claude plugin validate plugins/benchtrack-dev
✔ Validation passed                     (also exit 0 with --strict)

$ python plugins/sync_plugin.py --check          # after editing mcp-server/README.md only
Plugin copy is out of date; run `python plugins/sync_plugin.py`:
  differs: plugins/benchtrack-dev/mcp-server/README.md (from mcp-server/README.md)
$ python plugins/sync_plugin.py && python plugins/sync_plugin.py --check
Synced 12 files into plugins/benchtrack-dev/
Plugin copy is in sync (12 files).
```

## Limits

- **Hooks and permission rules are guardrails, not a sandbox.** They match the commands an agent writes; a script that opens `.env` by itself, or an unusual spelling, can get past them. Claude Code's [sandboxing](https://code.claude.com/docs/en/sandboxing) would be the OS-level layer.
- The guard is deliberately conservative. For example, `cp .env.example .env` is blocked; the human does it once, as in the README.
- The MCP server's read-only guarantee comes from its code. The staff token it uses can write through the API ([permissions](permissions.md#the-mcp-servers-token)).
