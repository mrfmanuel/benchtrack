# Agent security notes

How AI coding agents were used on BenchTrack, what they could access, how their actions were approved, the risks considered and the mitigations in place. Status as of 2026-10-21. Updated in Step 10, when the guardrail hooks, permission rules and read-only MCP server ([agent extension pack](../docs/agent-extension-pack.md)) were added. The current permission configuration is described in [`docs/permissions.md`](../docs/permissions.md).

## 1. Agents and what they could access

### (a) Claude Code CLI: implementation agent

| | |
|---|---|
| Where | The maintainer's Windows machine, started in the repository folder |
| Permission mode | **Default**: asks before running commands and before editing files; the maintainer approved each action interactively |
| Custom configuration | Until Step 9: none. **Since Step 10:** project [`.claude/settings.json`](../.claude/settings.json) with allow/ask/deny rules (deny `.env*`, destructive commands and `gh pr merge`; ask for `git push`, `docker compose down -v`, workflow edits, CI re-runs; allow tests and lints), a PreToolUse **guard hook** and a PostToolUse **ruff hook** ([`agent-hooks/`](../agent-hooks/)), and the read-only [`benchtrack` MCP server](../mcp-server/README.md). Details: [`docs/permissions.md`](../docs/permissions.md) |
| Could access | The repository working tree, including the git-ignored `.env` on disk (never printed or committed, see §3); local Docker (Compose stack, scanner containers); the `gh` CLI authenticated as the maintainer (token scopes `gist`, `read:org`, `repo`, `workflow`, checked with `gh auth status`, token not shown); web search and fetch for documentation |
| Also observed in this repo's workflow log | Claude Code used Claude in Chrome only against **local** dev servers (Step 4 UI smoke test, Step 9a CSP check on `127.0.0.1:8010`), and read-only `gh` / GitHub API calls during the deploy incident (names and dates of secrets only, never values) |

### (b) Claude in the Cowork desktop app: planner and reviewer

| | |
|---|---|
| Role | Planning the steps, reviewing results, operating web UIs |
| Could access | The project folder through a Linux VM bridge; the maintainer's **Chrome** via Claude in Chrome, **inside the logged-in GitHub and Render sessions** |
| Consequence | Anything the maintainer can do in GitHub or Render in that browser, the agent could attempt. Approval in chat and the platform's own permission classifier were the controls (see §2). |

## 2. Approval model, with real examples

| Action | What happened | Control |
|---|---|---|
| Every commit and push | Made by Claude Code, each approved by the maintainer | Default permission mode (interactive approval) |
| Production CD re-run during the deploy incident ([incident report](../ops/incidents/2026-10-21-deploy-not-applied.md)) | The Cowork agent clicked *Re-run all jobs* only after the maintainer's explicit "yes" in chat; diagnosis before that was read-only | Explicit approval in chat |
| `CLIENT_IP_HEADER` on Render (PR #1 merge precondition) | Set by the agent at the maintainer's request | Human request |
| Merging PR #1 | The agent tried to click *Merge pull request*; the agent platform's own permission classifier **blocked** it ("Merge Without Review"), so the maintainer merged it. **Human-only merge is now a rule.** | Platform classifier, then human |
| Production rate-limit probe ([PR audit F3](pr-audit-1.md)) | Approved by the maintainer. Cloudflare blocked the authorized method, so the agent changed it mid-way, **flagged the change before running it**, and documented both runs. | Explicit approval; deviation disclosed |

**Rules that came out of this:**
1. Humans merge to `main`. Agents may open PRs, push branches and comment.
2. Production changes (deploys, re-runs, Render settings, probes) need an explicit "yes" in chat for that specific action, and diagnosis stays read-only until then.
3. If an approved procedure has to change, the agent stops, explains, and records the deviation.

## 3. Risks considered and mitigations

| Risk | How it could happen here | Mitigations in place | Residual risk / gap |
|---|---|---|---|
| **Prompt injection** | Instructions hidden in repo files, issues, PR comments, CI logs or web pages read by an agent (both agents read web pages; Cowork reads GitHub/Render UIs) | Agents treat observed content as data; actions need human approval; production actions need an explicit "yes"; read-only diagnosis first | Since Step 10, the guard hook blocks the highest-risk actions deterministically, whatever the model was told (e.g. `cat .env`, force push, push to `main`), and frequent safe commands are allowed so prompts stay meaningful. Injection that stays within allowed actions is still possible. |
| **Secrets in prompts, logs and screenshots** | A token pasted into chat, echoed by a command, or visible in a screenshot. **A Swagger UI screenshot showed the local staff token, so it was kept out of the repo.** | Secrets never echoed (CD passes the hook via `env:`, only names listed); `.env` git-ignored and never committed; gitleaks over all history: 0 leaks; tracking codes masked in logs; `STAFF_TOKEN` hidden from config error output | Screenshots and chat transcripts are outside git and depend on human care (see [AI tool and data policy](ai-tool-data-policy.md)). |
| **Destructive commands** | `rm -rf`, `DROP`, `git push --force`, `docker system prune`, deleting volumes | AGENTS.md forbids them without asking; default permission mode asks before every command; integration tests refuse databases not named `*_test` | **Since Step 10:** deny rules plus the guard hook block `rm -rf`, `git push --force`, `git reset --hard`, `DROP TABLE`/`TRUNCATE`, `docker system prune`/`volume rm`; `docker compose down -v` asks. [Verified live](../docs/agent-extension-pack.md#real-example-session-2026-10-21) in a fresh session. Guardrails, not a sandbox. |
| **Malicious or typosquatted packages** | An agent suggests or installs a lookalike dependency | Dependencies via `uv add` / npm from the official registries, locked (`uv.lock`, `package-lock.json`), installed with `--locked` / `npm ci`; pip-audit, npm audit and Trivy clean ([scan findings](scan-findings.md)); new dependencies must be justified (policy) | Scanners only know published advisories; review of new packages is manual. |
| **Over-broad CI permissions** | A workflow or action with write access or a leaked token | `permissions: contents: read` in both workflows; actions pinned to commit SHAs; `persist-credentials: false`; the deploy hook is an Actions secret, never printed | The `gh` token used by Claude Code has `repo` and `workflow` scopes (it can push and edit workflows), so the interactive approval is what limits it. |
| **Browser agent inside logged-in sessions** | Cowork drives Chrome where GitHub and Render are logged in, so a wrong click or injected instruction acts with the maintainer's rights | Explicit approval for production actions; the platform classifier blocked an unreviewed merge; human-only merge rule | At the end of Step 9 `main` had no branch protection, so human-only merge was a process rule. The maintainer then enabled branch protection (PR required, 6 CI checks, no force pushes), and Step 10 added `gh pr merge` deny, `git push` ask and the guard's block on pushes to `main`; see [`docs/permissions.md`](../docs/permissions.md#3-human-only-merge-enforced-by-branch-protection) for how to verify it is active. The browser agent still acts with the maintainer's rights inside the logged-in UIs. |

**Other mitigations already in place:**
- The app fails fast at startup if `STAFF_TOKEN` is missing or shorter than 16 characters, and never logs it.
- Deploys only through CD after green CI, which verifies the deployed commit via `/api/health`.
- Security review of PRs ([PR #1 audit](pr-audit-1.md)), with findings fixed before merge.
- Guardrail hooks and permission rules (Step 10): see [`docs/permissions.md`](../docs/permissions.md). The MCP server gives agents read-only API access with a token they never see.

## 4. Recommendations (not yet done)

1. ~~**Protect `main`**~~ **Done (maintainer, after Step 9):** pull request required, 6 CI checks, no force pushes. Next: add the new `agent-pack` CI check to the required checks, and consider requiring one approving review.
2. ~~**Step 10 hooks**~~ **Done (Step 10):** guard hook and deny rules block destructive commands, `.env` access, secret printing, force pushes and pushes to `main` ([tests](../agent-hooks/tests/), CI job `agent-pack`).
3. **Narrower token for agents**: a fine-grained GitHub token limited to this repository, without `workflow` unless needed.
4. **Separate browser profile** for the browser agent, signed in only where needed.
