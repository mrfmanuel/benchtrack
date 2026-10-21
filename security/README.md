# Security

Index of BenchTrack's security artifacts. Operational procedures live in [`ops/`](../ops/).

| Artifact | What it is |
|---|---|
| [`pr-audit-1.md`](pr-audit-1.md) | Security review of PR #1 (HTTP hardening): findings F1–F11, including the forged `X-Forwarded-For` rate-limit bypass (High, fixed) and its production verification |
| [`scan-findings.md`](scan-findings.md) | Triage of every deterministic scan: Semgrep, pip-audit, npm audit, gitleaks, Trivy (S1–S6), with commands and limits |
| [`scans/`](scans/) | Raw scanner outputs (JSON; Trivy also as a table), unmodified |
| [`agent-security-notes.md`](agent-security-notes.md) | Which AI agents were used, what they could access, the approval model with real examples, risks, mitigations and gaps |
| [`ai-tool-data-policy.md`](ai-tool-data-policy.md) | Which AI tools are allowed, what data may never be shared with them, human review before merge and production actions, verification of AI-generated code, dependency rules |

## Related

- [`ops/runbook.md`](../ops/runbook.md): start/stop, health and version, logs, deploy and rollback, seeding, rotating `STAFF_TOKEN`, free-tier limits
- [`ops/incidents/`](../ops/incidents/): incident reports, e.g. [2026-10-21 deploy not applied](../ops/incidents/2026-10-21-deploy-not-applied.md)
- [`docs/deployment.md`](../docs/deployment.md): Render setup and deploy troubleshooting
- [`docs/testing.md`](../docs/testing.md): test layers and the checks that run in CI

## Security controls at a glance

- **Auth:** bearer `STAFF_TOKEN` on all staff routes (constant-time compare); the app refuses to start without a token of at least 16 characters.
- **Public route:** whitelist response model (no PII, no notes, no cost); 10 lookups/min per client keyed on the Cloudflare-supplied IP, never `X-Forwarded-For`; unguessable tracking codes from `secrets`.
- **HTTP:** per-path CSP, `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, Permissions-Policy, HSTS over HTTPS, `Cache-Control: no-store` on the API.
- **Logs:** JSON, tracking codes masked.
- **Container:** non-root user, no setuid/setgid binaries, `no-new-privileges` in Compose, health check.
- **CI/CD:** SHA-pinned actions, `contents: read`, Semgrep on every PR, deploy only after green CI, deployed commit verified.

## Reporting a problem

Open a private security advisory on the GitHub repository, or contact the maintainer directly. Never post secrets or real customer data in an issue.
