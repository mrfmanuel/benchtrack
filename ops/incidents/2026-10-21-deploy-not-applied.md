# Incident 2026-10-21: commit `fbfa3fa` not deployed (silently stale production)

| | |
|---|---|
| Status | **Resolved** 2026-10-21 05:40:44 UTC |
| Severity | Low: no user impact. The risk was production silently running stale code while CI/CD looked green. |
| Service | https://benchtrack.onrender.com (Render web service + Render PostgreSQL) |
| Detected by | Human: `/api/health` returned no `version` field after `fbfa3fa` was pushed |
| Diagnosis | AI agents, read-only (values of secrets and variables never read) |
| Recovery | Re-run of CD #3, explicitly authorized by the human in chat |

## Summary

`fbfa3fa` added `version` to `GET /api/health` so CD can verify which commit is live. CI #3 passed, but CD #3 (run `39547963243`) ran before the `RENDER_DEPLOY_HOOK_URL` secret existed. As designed, it skipped the deploy in 6 s and showed a **green** ✓ with only a notice. The human then added the secret and the `APP_URL` variable, but adding a secret does not trigger CD, and CD was not re-run at that point. Production therefore kept serving the first manual deploy. After a read-only diagnosis, the human authorized re-running CD #3; the re-run deployed `fbfa3fa` and verified it live in 1m24s.

## Timeline (UTC, 2026-10-21)

| Time | Event |
|---|---|
| before 04:35 | First production deploy, made by hand on Render (before `version` existed). |
| 04:37:44, 04:39:26 | CD #1 and #2 (for `19d61f9`, `2ef11ab`) skip: secret not set yet. Expected at that point. |
| 05:08:21 | `fbfa3fa` pushed; **CI #3** (`39547870318`) passes all 6 jobs. |
| 05:09:24–05:09:30 | **CD #3** (`39547963243`, attempt 1) finds the secret empty: notice "The RENDER_DEPLOY_HOOK_URL secret is not set", the deploy and verification steps are skipped, conclusion **success** (6 s). |
| 05:18:29 | Human creates the secret `RENDER_DEPLOY_HOOK_URL`. |
| 05:20:02 | Human sets the variable `APP_URL`. CD is not re-run: nothing deploys. |
| ~05:33 | Human notices `/api/health` → `{"status":"ok","database":"ok"}` (no `version`) and reports the incident. |
| 05:33–05:36 | Read-only diagnosis. Claude in Chrome checks the Actions runs, the CD annotations and that the secret and variable exist (values not read). Claude Code confirms the same with `gh` / the GitHub API and `curl`. Root cause identified; re-run of CD #3 proposed. |
| (before 05:39) | **Human authorizes the re-run explicitly in chat.** |
| 05:39:20 | Agent clicks **Re-run all jobs** on CD #3 (attempt 2, triggered under the human's GitHub account). |
| 05:39:25 | Deploy hook → `HTTP 200`; Render builds `main` (`fbfa3fa`). |
| 05:40:44 | CD #3 attempt 2 **succeeds** (1m24s): `/api/health` reports `fbfa3fab…` on poll attempt 6 (75 s). Notice: `fbfa3fab1cba94ffe9b6fddb05ab56d68506c25b is live at https://benchtrack.onrender.com`. |
| 05:45:18 | Independent check: production health shows the expected version. **Resolved.** |

Time to detect: ~24 min after CD #3 skipped. Time to recover after authorization: 1m24s.

## User impact

- **Customers and staff: none.** The old version stayed up and healthy throughout (`200`, `database: ok`), and no data was lost. The commits it was missing change CI/CD, docs, the container health-check script and the health `version` field, none of them user-facing.
- **Risk:** production was silently stale while every run in the Actions list was green. A user-facing fix pushed in this state would not have shipped, and nothing would have said so loudly.

## Evidence

Read-only commands. Secret values were never requested or printed: `gh secret list` returns names and dates only, and the Actions UI never shows secret values.

**Before recovery (05:33 UTC):**

```text
$ gh run list --limit 6 --json ... --jq '...'
2026-10-21T05:09:24Z CD workflow_run completed/success attempt=1 sha=fbfa3fa id=39547963243 CD
2026-10-21T05:08:21Z CI push completed/success attempt=1 sha=fbfa3fa id=39547870318 Expose version in health check; CD verifies deployed commit
2026-10-21T04:39:26Z CD workflow_run completed/success attempt=1 sha=2ef11ab id=39545230399 CD
...

$ gh run view 39547963243 --json ... --jq '...'
created=2026-10-21T05:09:24Z updated=2026-10-21T05:09:30Z attempt=1 conclusion=success
job Deploy to Render: success 2026-10-21T05:09:27Z→2026-10-21T05:09:29Z
  step 2 Check deploy configuration: success
  step 3 Trigger Render deploy: skipped
  step 4 Wait for the new commit to be live: skipped
annotation: "Deploy skipped: The RENDER_DEPLOY_HOOK_URL secret is not set, so nothing was deployed."

$ gh secret list
RENDER_DEPLOY_HOOK_URL	2026-10-21T05:18:29Z          # value: [REDACTED, never read]
$ gh variable list --json name,updatedAt
APP_URL updated=2026-10-21T05:20:02Z

$ gh api "repos/mrfmanuel/benchtrack/actions/runs?created=>=2026-10-21T05:10:00Z" --jq '.total_count'
0                                                      # nothing ran after the configuration

$ curl.exe -sS -i https://benchtrack.onrender.com/api/health
HTTP/1.1 200 OK
Date: Wed, 21 Oct 2026 05:33:44 GMT
{"status":"ok","database":"ok"}                        # no "version": pre-fbfa3fa build

$ git rev-parse origin/main
fbfa3fab1cba94ffe9b6fddb05ab56d68506c25b
```

**After recovery (05:45 UTC):**

```text
$ gh api repos/mrfmanuel/benchtrack/actions/runs/39547963243/attempts/{1,2} --jq '...'
attempt 1: completed/success started=2026-10-21T05:09:24Z updated=2026-10-21T05:09:30Z
attempt 2: completed/success started=2026-10-21T05:39:20Z updated=2026-10-21T05:40:44Z

$ gh run view 39547963243 --json jobs --jq '...'
  step 3 Trigger Render deploy: success
  step 4 Wait for the new commit to be live: success

$ gh run view 39547963243 --log | grep ...
Deploy hook responded with HTTP 200
Waiting for https://benchtrack.onrender.com/api/health to report version fbfa3fab1cba94ffe9b6fddb05ab56d68506c25b
Deployed version: fbfa3fab1cba94ffe9b6fddb05ab56d68506c25b (healthy after attempt 6, 75s)
##[notice]fbfa3fab1cba94ffe9b6fddb05ab56d68506c25b is live at https://benchtrack.onrender.com
```

## Root cause

**Configuration order, not a code defect.** CD runs only when a CI run on `main` completes, and it reads the secret at that moment. CD #3 ran at 05:09:24, nine minutes before the secret was created, so it skipped the deploy by design. Adding the secret later does not start a new run, and the existing run was not re-run, so `fbfa3fa` never reached Render.

**Why it went unnoticed: a skipped deploy looked like a successful one.** The skip was reported as a `notice` on a `success` run, which shows as a green ✓ CD in the Actions list. Render's auto-deploy is off (CD is the only deploy path), so nothing else would have shipped the commit.

## Action proposed

1. Re-run CD #3 (`39547963243`): *Re-run all jobs*, equivalent to `gh run rerun 39547963243`. The re-run reads the now-configured secret and variable, POSTs the hook (Render builds `main` = `fbfa3fa`), and polls `/api/health` until `version == fbfa3fab1cba94ffe9b6fddb05ab56d68506c25b`. This changes production, so it was not executed without approval.
2. Make a skipped deploy impossible to miss (see *Lessons learned*).

## What the human authorized

Re-running CD #3 (run `39547963243`) to deploy `fbfa3fa` to production, given explicitly in chat after reviewing the diagnosis. Nothing else was authorized: no changes to Render settings, secrets, variables or the database.

## What was executed

- The agent (Claude in Chrome, in the human's browser session) clicked **Re-run all jobs** on CD #3 at 05:39:20 UTC. That was the only production-changing action.
- The re-run triggered the Render deploy hook (`HTTP 200`); Render built and deployed `fbfa3fa`; CD verified the version.
- No secrets were read, printed or changed.

## Verification

- CD #3 attempt 2: **success** in 1m24s, with notice `fbfa3fab… is live at https://benchtrack.onrender.com`.
- Independent check at 05:45:18 UTC:

  ```text
  $ curl.exe -sS -i https://benchtrack.onrender.com/api/health
  HTTP/1.1 200 OK
  Date: Wed, 21 Oct 2026 05:45:18 GMT
  {"status":"ok","database":"ok","version":"fbfa3fab1cba94ffe9b6fddb05ab56d68506c25b"}
  ```

  The version equals `git rev-parse origin/main`.

## Lessons learned

1. **A skipped CD must not look like a deploy.** Done in the commit that added this report: on a push to `main` with the secret missing, `cd.yml` now emits a `::warning` annotation titled **NOT DEPLOYED** that names the commit, and writes a job summary `## ⚠️ NOT DEPLOYED` explaining that production keeps the previous version and how to recover (*Re-run all jobs*). The run stays green on purpose, because CD may legitimately be unconfigured. Successful and failed verifications now also write a summary line (`✅ Deployed <sha>` / `❌ Deploy NOT verified`).
2. **Changing CD configuration requires a deploy action.** Adding or rotating `RENDER_DEPLOY_HOOK_URL` is not picked up by past runs; re-run the latest CD run on `main`. This is documented in [`docs/deployment.md`](../../docs/deployment.md#deploy-troubleshooting).
3. **Verify by version, not by "healthy".** The old build was perfectly healthy; only the `version` field from `fbfa3fa` exposed the problem. CD and the runbook check `version == commit`.
4. **Approval gate worked.** The diagnosis stayed read-only, and the only production change ran after explicit human approval in chat.

Follow-up, not done and not authorized: add a `workflow_dispatch` trigger to `cd.yml`, so a deploy can be started without re-running an old run.
