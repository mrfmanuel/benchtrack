# Permissions for AI agents

How Claude Code sessions in this repository are limited, and why. The pieces are described in [`docs/agent-extension-pack.md`](agent-extension-pack.md). The risks they answer, and the approval history behind them, are in [`security/agent-security-notes.md`](../security/agent-security-notes.md). What data may reach an AI tool at all is set by the [AI tool and data policy](../security/ai-tool-data-policy.md).

## Layers

| Layer | Where | Enforced by | Stops |
|---|---|---|---|
| 1. Permission rules: allow / ask / deny | [`.claude/settings.json`](../.claude/settings.json) | Claude Code | Matching tool calls, by rule |
| 2. PreToolUse guard hook | [`agent-hooks/guard.py`](../agent-hooks/guard.py), wired in the same file | Our code, before every Bash/PowerShell/file call | Secrets access, destructive commands, pushes to `main`, with a reason |
| 3. PostToolUse ruff hook | [`agent-hooks/ruff_check.py`](../agent-hooks/ruff_check.py) | Our code, after Python edits | Lint problems slipping through (feedback, not a block) |
| 4. Interactive approval | Claude Code default mode | The human | Anything not explicitly allowed |
| 5. Branch protection on `main` | GitHub | GitHub | Any change to `main` without a PR, green CI and a human merge |
| 6. Least-privilege CI and tokens | `.github/workflows/`, MCP server | GitHub, our code | Workflows or tools doing more than reading |

Each layer assumes the others can fail. A wrong allow rule is still caught by the guard, a guard gap is still caught by deny rules and approval, and anything that reaches git still can't land on `main` without review.

## 1. The allow / ask / deny model

Claude Code evaluates **deny → ask → allow**; the first match wins, and a broader deny can't be overridden by a narrower allow. PreToolUse hooks run before the permission check, but deny and ask rules still apply even if a hook allows. Anything that matches no rule falls back to **ask** (default mode).

| Decision | Rules (abridged) | Why |
|---|---|---|
| **Deny** | `Read`/`Edit` of `.env`, `.env.*`, `.envrc` (carve-out `!.env.example`); `rm -rf`/`-fr`; `git push --force`/`-f`/`--force-with-lease`; `git reset --hard`; `docker system prune`, `docker volume rm`/`prune`; `printenv`; `gh pr merge` | Secrets and irreversible actions. There is no case where an agent should do these on its own: a human runs them deliberately. `Read` deny rules also cover recognised shell readers such as `cat .env`. **`gh pr merge` is denied: humans merge.** |
| **Ask** | `git push` (any); `docker compose down -v` / `--volumes`; `Edit(.github/workflows/**)`; `gh workflow run`, `gh run rerun` | Outward-facing or hard to undo, but legitimate when the human agrees each time: publishing a branch, wiping the local database, changing CI/CD (which holds the deploy secret), triggering CI/CD or a production re-deploy. |
| **Allow** | `uv run pytest`, `uv run ruff check/format`, `npm test`, `npm run lint/typecheck/build`, `npx vitest run`, Redocly lint, `python -m unittest discover`, `python plugins/sync_plugin.py --check`, `git status/diff/log` | Read-only or test-only commands that run constantly. Prompting for each one trains people to click "yes" without reading. |

The **guard hook** covers what prefix rules can't express:
- forms Claude Code doesn't split, such as `bash -c '…'`, `$(…)`, `uv run python -c …` and `docker compose exec app printenv`;
- every spelling of `rm -rf`, including inside `find -exec`;
- pushes to `main` via `HEAD:main` or a bare `git push` while on `main`;
- printing secret-named variables;
- `docker compose config` (which prints `.env` values) and `docker inspect` of the environment.

It answers with a specific reason the agent can act on (e.g. *"Push a feature branch and open a PR"*). If the guard itself fails or times out, `onFailure: "block"` refuses the call.

**Why not deny `Bash` entirely, or allow everything?** The agent needs a shell to run tests and builds; that is most of the value. Allowing everything would rely on the model behaving, and [the docs are explicit](https://code.claude.com/docs/en/permissions) that permission rules, not prompts, are what Claude Code enforces.

**Known limits:**
- Rules and hooks match the command text. A program that opens `.env` by itself, or an exotic spelling, can get past both; OS-level [sandboxing](https://code.claude.com/docs/en/sandboxing) is the next layer if needed.
- Personal `.claude/settings.local.json` files can add rules. Project deny rules still win.

## 2. The MCP server's token

The [`benchtrack` MCP server](../mcp-server/README.md) takes `BENCHTRACK_TOKEN` from the environment of the shell that starts Claude Code. [`.mcp.json`](../.mcp.json) only contains `${BENCHTRACK_URL}`/`${BENCHTRACK_TOKEN}` expansions, never values.

- **Scope of the credential: full staff access.** BenchTrack has a single staff role (spec §5), so the token that reads the dashboard can also create tickets, change status and add notes through the API. There is no read-only token today.
- **Scope of the server: read-only.** It exposes five GET-only tools (`health`, `dashboard`, `list_tickets`, `get_ticket`, `track`), no write tools, all annotated `readOnlyHint`, with tests asserting both. So the restriction is enforced by the server's code, not by the credential: anyone who obtains the token can still write through the API directly.
- **Handling:** sent only in the `Authorization` header of staff calls. It is never logged, never returned, never put in a URL, and scrubbed from errors (tested). Every call has a timeout.
- **Use local or demo data only.** Tool results (customer names, phones, notes) are sent to the AI provider. Point the server at the local Compose app or another environment with fictional data, and never give an agent session the production token ([AI policy](../security/ai-tool-data-policy.md)).
- **Improvement (not done):** a separate read-only API token or role, so a leaked agent token couldn't write. That is a contract and spec change (§5).

The `gh` CLI token on the maintainer's machine (`repo`, `workflow` scopes) is also reachable by Claude Code through Bash. The ask rules on `git push`, `gh workflow run` and `gh run rerun`, the deny on `gh pr merge`, and branch protection limit what it can be used for. A fine-grained, repository-only token would narrow it further ([agent security notes](../security/agent-security-notes.md#4-recommendations-not-yet-done)).

## 3. Human-only merge, enforced by branch protection

The rule *"humans merge to `main`; agents open PRs"* (from the PR #1 merge attempt, see the [agent security notes](../security/agent-security-notes.md#2-approval-model-with-real-examples)) is enforced in three places:

1. **GitHub branch protection on `main`:** a pull request is required, the **6 CI checks** must pass (Contract, Backend, Integration, Frontend, Docker image, Semgrep), and force pushes are not allowed. Agents can't push to `main` at all, so every change goes through a PR. The PR #1 merge attempt was also blocked by the agent platform's own classifier ("Merge Without Review").
2. `.claude/settings.json` denies `gh pr merge` and asks before any `git push`.
3. The guard blocks pushes to `main` and force pushes before they reach GitHub.

The new `agent-pack` CI job (hook, MCP and plugin checks) should be added to the required checks once this PR is merged.

**Verify the protection is active** (it must report `true` and list the checks):

```bash
gh api repos/mrfmanuel/benchtrack/branches/main --jq .protected
gh api repos/mrfmanuel/benchtrack/branches/main/protection \
  --jq '{checks: .required_status_checks.contexts, force_push: .allow_force_pushes.enabled}'
```

If you use a *ruleset* instead of classic protection, check it with `gh api repos/mrfmanuel/benchtrack/rules/branches/main`.

## 4. Relation to the agent security notes

[`security/agent-security-notes.md`](../security/agent-security-notes.md) records which agents were used, what they could reach, and the real approval history: the deploy re-run, the blocked merge, the probe deviation. That history explains why these rules exist. This document is the **current configuration**. Changing a rule here means:

1. Update `.claude/settings.json` and/or `agent-hooks/guard.py`, with tests (`agent-hooks/tests/`) and `python plugins/sync_plugin.py`.
2. Update this file and, if the risk picture changes, the agent security notes.
3. Treat it as a security-relevant change: open a PR and have a human review it.
