# Security audit: PR #1 `security/http-hardening`

| | |
|---|---|
| PR | [#1 Add security headers and stop trusting X-Forwarded-For for rate limiting](https://github.com/mrfmanuel/benchtrack/pull/1) |
| Branch / base | `security/http-hardening` → `main` (`72c9e20`) |
| Audit date | 2026-10-21 |
| Auditor | AI agent (Claude Code). A `/security-review` command was not available in this session, so the review was done manually with the method below. Reviewed by the human, who merged the PR on 2026-10-21. |
| Result | 2 findings fixed in this PR (1 High, 1 Medium), 3 Low fixed, 1 Medium accepted with a merge precondition (met, verified in production), 5 informational. No auth bypass, no PII exposure on public routes, no injection, no secrets. |

## Scope

The full diff `git diff main...security/http-hardening`:

- `backend/app/security_headers.py` (new): CSP per path, common security headers, HSTS, `Cache-Control`, and `ForwardedProtoMiddleware` (added by this audit)
- `backend/app/services/client_ip.py` (new), `backend/app/deps.py`, `backend/app/config.py`: rate-limit client key, `CLIENT_IP_HEADER`
- `backend/app/main.py`, `backend/app/errors.py`, `backend/app/routers/docs.py`: middleware wiring, 500 headers, hashable Swagger init script
- `docker/entrypoint.sh`: uvicorn proxy-header flags
- `.github/workflows/ci.yml`: container-level header and rate-limit checks
- tests, docs (`deployment.md`, `testing.md`, README, AGENTS, `.env.example`)

Focus areas requested: auth bypass, PII on public routes, injection, CSP gaps, rate-limit bypass via `X-Forwarded-For` spoofing, secrets.

Out of scope: the frontend code (unchanged in this PR, but it was checked for CSP compatibility), Render and Cloudflare configuration (not readable from here), dependency CVEs (Semgrep in CI covers code patterns only).

## Method

1. **Diff review:** read every changed line; traced each request path (API, `/docs`, SPA fallback, static assets, error handlers, unhandled 500) through the middleware stack.
2. **Upstream behaviour:** read uvicorn 0.54.0 `uvicorn/middleware/proxy_headers.py` (`_TrustedHosts.get_trusted_client_address`) and Starlette's middleware ordering. Checked Render's documented `X-Forwarded-For` behaviour: [Render feedback: "Send the correct X_FORWARDED_FOR"](https://feedback.render.com/features/p/send-the-correct-xforwardedfor), [Render community: client IPs](https://community.render.com/t/accessing-client-ips-in-a-node-express-app/36282).
3. **Reproduction on the real container** (Docker Compose, `127.0.0.1:8010`): the `main` image first, then the branch image.
4. **Browser check (Chrome):** `/docs` and the SPA under the new CSP, with a `securitypolicyviolation` listener, the console, Swagger "Try it out", and a positive control (an injected inline script must be blocked).
5. **Static checks:** Semgrep 1.182.0 `--config auto --error` → 0 findings; ruff; actionlint; a grep of the diff for secrets.
6. **Tests:** backend 536 passed (unit 281, API 255), integration 10 passed, frontend 135 passed. CI on the PR: all 6 jobs green.

## Findings

### F1 — High — Public rate limit bypassable with a forged `X-Forwarded-For`: **fixed in this PR**

- **Where (on `main`):** `docker/entrypoint.sh:15-16` (`--proxy-headers --forwarded-allow-ips='*'`), `backend/app/deps.py:25` (`request.client.host`).
- **What:** with `forwarded_allow_ips='*'`, uvicorn trusts every hop and returns the **leftmost** `X-Forwarded-For` entry:

  ```python
  # uvicorn/middleware/proxy_headers.py (0.54.0), get_trusted_client_address
  if self.always_trust:
      return _parse_host_port(x_forwarded_for_hosts[0])
  ```

  Render's proxy appends to a client-supplied `X-Forwarded-For` instead of replacing it, so the leftmost entry is attacker-controlled. Each request with a new fake IP got a fresh bucket, which disabled the 10 lookups/min limit (spec §9.14), the only control against guessing tracking codes on `/api/public/track/{code}`.
- **Evidence (the `main` image, real uvicorn):**

  ```text
  forged X-Forwarded-For per request (15 lookups):
   200 200 200 200 200 200 200 200 200 200 200 200 200 200 200
  same requests without the header:
   200 200 200 200 200 200 200 200 200 200 429 429
  ```

- **Impact:** unlimited tracking-code enumeration (30⁵ ≈ 24.3 M codes). A hit reveals device brand/model and status history (no PII by design, spec §9.13), plus unbounded DB load from the public endpoint. Rated High as a full bypass of a spec-mandated security control; the data impact is limited.
- **Resolution:** `docker/entrypoint.sh:18` runs uvicorn with `--no-proxy-headers`. The limiter key comes from `backend/app/services/client_ip.py:41` (`rate_limit_key`): the TCP peer, or a single header the edge **overwrites** (`CLIENT_IP_HEADER`), never `X-Forwarded-For`. `backend/app/config.py:83` refuses `CLIENT_IP_HEADER=X-Forwarded-For` at startup.
- **Verification:** the branch image returns `200 ×10, 429, 429` for the same forged requests. Tests: `tests/unit/test_client_ip.py`, `tests/api/test_security_headers.py::test_forged_x_forwarded_for_*`. The CI `docker` job repeats the forged-header check against the real container, because `TestClient` does not run uvicorn's proxy middleware.

### F2 — Medium — `http://` redirects behind the TLS proxy (introduced by the F1 fix): **fixed in this PR**

- **Where:** a side effect of `--no-proxy-headers` (first commit of this PR). Fixed in `backend/app/security_headers.py:107` (`ForwardedProtoMiddleware`), wired at `backend/app/main.py:63`.
- **What:** without uvicorn's proxy headers, the app saw `scheme=http` on Render, so absolute URLs it builds (FastAPI's trailing-slash redirect) pointed to `http://`. The redirect would cross to plain HTTP: browsers drop `Authorization` on such hops, and it is a downgrade even if Cloudflare redirects back.
- **Evidence (branch image before the fix):**

  ```text
  $ curl -i -H "X-Forwarded-Proto: https" http://127.0.0.1:8010/api/tickets/
  HTTP/1.1 307 Temporary Redirect
  location: http://127.0.0.1:8010/api/tickets
  ```

- **Resolution:** a pure ASGI middleware restores **only the scheme** from the rightmost `X-Forwarded-Proto`. Forging it can only make the server believe the request is HTTPS (https absolute URLs and HSTS on the forger's own plain-HTTP response, which browsers ignore), and it never touches the client address.
- **Verification:** `location: https://127.0.0.1:8010/api/tickets` with the header and `http://…` without it. Tests: `test_trailing_slash_redirect_keeps_https_behind_the_proxy`, `test_redirect_stays_http_without_a_tls_proxy`, `test_forwarded_proto_does_not_change_the_client_address`, and `test_forwarded_proto_middleware_sets_the_scheme` (5 cases, including `wss`).

### F3 — Medium — Production depends on `CLIENT_IP_HEADER`: **accepted, with a merge precondition**

- **Where:** `backend/app/services/client_ip.py:41-45`, `backend/app/main.py:69-70`, `docs/deployment.md` (environment table).
- **What:** two residual risks of the F1 fix:
  1. **Missing configuration → availability.** On Render, without `CLIENT_IP_HEADER` the TCP peer is Render's proxy, so all clients share one bucket: about 10 public lookups per minute *in total*. Anyone could keep the tracking page in `429` for everybody.
  2. **Trust in `CF-Connecting-IP`.** Safe only if every request reaches the app through Cloudflare, which overwrites that header. Render serves `onrender.com` through Cloudflare (`Server: cloudflare`, `CF-RAY` on production responses), but Render does not document or guarantee the header. If the origin were reachable without Cloudflare, the header would be forgeable like `X-Forwarded-For`.
- **Mitigations in this PR:** the app logs a warning at startup when running on Render (`RENDER_GIT_COMMIT` set) without `CLIENT_IP_HEADER` (`main.py:69`). It refuses `X-Forwarded-For` as the header, and falls back to the peer on a missing or malformed header value. Deployment docs and troubleshooting row added.
- **Reason for accepting:** this is the best signal Render offers. The alternative (counting proxy hops from the right of `X-Forwarded-For`) depends on an undocumented hop count and was rejected.
- **Required before merge:** set `CLIENT_IP_HEADER=CF-Connecting-IP` on the Render web service.
- **Post-deploy verification: done 2026-10-21, see below.**

#### F3 verification in production (2026-10-21)

**Preconditions (by the human):** `CLIENT_IP_HEADER=CF-Connecting-IP` set on the Render web service; PR #1 reviewed and merged (`987a7fc`, 06:15:39Z); CI and CD green (CD 06:16:45Z). The human explicitly authorized the probe in chat. The agent ran it from one workstation, against one public tracking code from the fictional seed data.

```text
$ curl -sS https://benchtrack.onrender.com/api/health          # 06:19:15Z
{"status":"ok","database":"ok","version":"987a7fc4b43117698c38339306120a88b25dbfcf"}
```

**Probe 1, as authorized: forged `X-Forwarded-For` and forged `CF-Connecting-IP` on each request.** All requests were rejected by **Cloudflare** before reaching Render or the app: `Server: cloudflare`, `error code: 1000`, and none of the app's headers.

```text
06:19:25 #1  XFF=198.51.100.1  CF=203.0.113.1  -> 403
...                                                (#2–#10 identical)
06:19:27 #11 XFF=198.51.100.11 CF=203.0.113.11 -> 403
$ curl -i -H "X-Forwarded-For: 198.51.100.50" -H "CF-Connecting-IP: 203.0.113.50" .../api/public/track/BT-DEM22
HTTP/1.1 403 Forbidden
Content-Type: text/plain; charset=UTF-8
Server: cloudflare
CF-RAY: a4de26c419bd7df0-SJO
error code: 1000
```

So a client **cannot** inject `CF-Connecting-IP`: Cloudflare refuses requests that already carry it. This is the strongest available evidence for F3's trust assumption. It also means this probe could not exercise the app's limiter.

**Probe 2: forged `X-Forwarded-For` only.** Same endpoint, count and forged addresses, without the header Cloudflare blocks. The change was disclosed to the human in the session.

```text
06:19:49 #1  XFF=198.51.100.1  -> 200   (app headers present)
...                                     (#2–#10: 200)
06:19:52 #10 XFF=198.51.100.10 -> 200
06:19:52 #11 XFF=198.51.100.11 -> 429   retry-after: 57
{"error":{"code":"rate_limited","message":"Too many requests. Try again in 57 seconds."}}
```

On `main` before PR #1, the same pattern returned 200 for every request (F1). The forged addresses now land in one bucket: the real client IP that Cloudflare put in `CF-Connecting-IP`.

**Recovery after the window:**

```text
06:21:13 $ curl -i https://benchtrack.onrender.com/api/public/track/BT-DEM22
HTTP/1.1 200 OK
Cache-Control: no-store
content-security-policy: default-src 'none'; frame-ancestors 'none'
strict-transport-security: max-age=31536000; includeSubDomains
x-frame-options: DENY
{"tracking_code":"BT-DEM22","device_type":"laptop",...,"status":"received",...}
```

HSTS on the production response also confirms F2's `X-Forwarded-Proto` handling behind Render.

**Result: F3 verified.** The limiter keys on the Cloudflare-supplied client IP, forged `X-Forwarded-For` is ignored, `CF-Connecting-IP` cannot be forged through Cloudflare, and normal lookups work after the window. Not checked from here: the absence of the startup warning in the Render logs, which the agent cannot read. The 429 after 10 lookups shows the header is in use; without it, the key would be Render's proxy address, which is shared but would give the same pattern from a single client. The Cloudflare 403 on forged headers and the configured variable together cover that.

### F4 — Low — IPv6 address rotation inside one /64: **fixed in this PR**

- **Where:** `backend/app/services/client_ip.py:20,35-38`.
- **What:** an IPv6 client typically controls a whole /64 (2⁶⁴ addresses), so keying by full address would allow rotation around the limit once real client IPs are used.
- **Resolution:** IPv6 keys are the /64 network; IPv4-mapped IPv6 addresses are treated as IPv4. Tests: `test_ipv6_clients_are_keyed_by_their_64`, `test_ipv4_mapped_ipv6_is_treated_as_ipv4`.

### F5 — Low — Unhandled 500 responses would miss the security headers: **fixed in this PR**

- **Where:** `backend/app/errors.py:142`.
- **What:** Starlette answers unhandled exceptions in `ServerErrorMiddleware`, outside user middleware, so a 500 would have had no CSP, nosniff or `no-store`.
- **Resolution:** the 500 handler adds `security_headers(request.scope)`. Test: `test_unhandled_error_500_still_has_headers`.

### F6 — Low — Swagger UI contacted `validator.swagger.io`: **fixed in this PR**

- **Where:** `backend/app/routers/docs.py:24-27`.
- **What:** by default Swagger UI loads a validator badge from `validator.swagger.io`, which sends the spec URL to a third party (and would have needed a CSP exception).
- **Resolution:** `validatorUrl: null`. Test: `test_swagger_does_not_call_the_external_validator`.

### F7 — Info — CSP design review (no gaps found)

- **SPA** (`security_headers.py:43`): `'self'` only, with no `unsafe-inline`/`unsafe-eval`, `object-src 'none'`, `base-uri 'none'`, `frame-ancestors 'none'`. The Vite build has no inline scripts or styles, and the bundle has no `eval`/`new Function`. React sets styles through the CSSOM, which `style-src` does not restrict.
- **`/docs`** (`security_headers.py:53`): the CDN files are allowed by **exact URL** at the pinned version, not by host. `cdn.jsdelivr.net` serves any npm or GitHub content, so a host-wide allowlist would be a known CSP bypass. The inline init script is allowed by a sha256 hash that is computed from the same constant that renders it (`test_docs_hash_covers_the_inline_script_actually_served`), and both CDN files keep their SRI hashes. `img-src data:` is needed for `swagger-ui.css` icons; data: images cannot run script. Accepted.
- **API** (`security_headers.py:42`): `default-src 'none'`.
- **Browser evidence:** with Chrome against the container, Swagger UI loaded 14 operations, expanded `/api/health`, and "Try it out" returned `{"status":"ok",…}` with **0 violations and no console errors**. The SPA `/track/BT-DEM22` rendered with **0 violations**. Positive control: an injected inline `<script>` did **not** run and fired `script-src-elem` (proves enforcement and that the listener works).
- `frame-ancestors 'none'` plus `X-Frame-Options: DENY` cover clickjacking. `Referrer-Policy: no-referrer` keeps tracking codes in `/track/<code>` URLs out of `Referer`.

### F8 — Info — Not added: Trusted Types, COOP/CORP

`require-trusted-types-for 'script'`, `Cross-Origin-Opener-Policy` and `Cross-Origin-Resource-Policy` would add defence in depth but were not requested. Trusted Types needs a compatibility check with React and Swagger UI. Accepted; candidate for a follow-up.

### F9 — Info — Access logs now show the proxy address

With `--no-proxy-headers`, uvicorn access logs record the TCP peer (Render's proxy) instead of the leftmost `X-Forwarded-For` value, which was attacker-controlled anyway. This is less forensic detail but also less PII in logs. Accepted.

### F10 — Info — In-memory, per-process limiter (pre-existing)

Limits multiply with the number of instances or workers (currently 1 on Render free). Memory is bounded: stale keys are pruned after the 60 s window (`services/rate_limit.py`), even under a flood of distinct keys. Accepted.

### F11 — Info — Focus areas with no findings

- **Auth bypass:** none. The middlewares only add or replace response headers and, for the scheme, adjust `scope["scheme"]`; neither short-circuits a request or touches `Authorization`. No routes were added. The SPA fallback answers only GET/HEAD 404s outside `/api` and `/assets`. Staff routes keep the bearer dependency (`tests/api/test_auth_and_errors.py` checks every staff operation in the contract). Staff endpoints have no brute-force limit, but the token is at least 16 characters (32 random URL-safe bytes recommended), so this is pre-existing and accepted.
- **PII on public routes:** none. Public responses are unchanged (whitelist model, contract-parity test). This PR adds `Cache-Control: no-store` to all `/api/*`, so tracking results and staff data are not kept in browser or shared caches.
- **Injection:** none. All header values are constants or computed from constants. `CLIENT_IP_HEADER` values are parsed with `ipaddress` and never reflected. `X-Forwarded-Proto` is only compared with `"https"`. The startup warning is static text. A pre-existing note: redirect `Location` uses the request `Host`, which is not exploitable behind Render/Cloudflare host routing.
- **Secrets:** none. The diff has no credentials; CI uses a fictional throwaway token. Semgrep `--config auto` found 0 issues, and a grep for key/secret/token/password assignments matched only a pre-existing fictional test string.

## Summary of resolutions

| ID | Severity | Title | Resolution |
|---|---|---|---|
| F1 | High | Rate limit bypass via forged `X-Forwarded-For` | Fixed in this PR |
| F2 | Medium | `http://` redirects behind TLS proxy (from the F1 fix) | Fixed in this PR |
| F3 | Medium | Production depends on `CLIENT_IP_HEADER` / Cloudflare | Accepted. Precondition met (human set it before merge); **verified in production 2026-10-21**: forged XFF → 429 on the 11th, forged `CF-Connecting-IP` blocked by Cloudflare (403, error 1000) |
| F4 | Low | IPv6 /64 rotation | Fixed in this PR |
| F5 | Low | 500 responses without security headers | Fixed in this PR |
| F6 | Low | Swagger validator third-party call | Fixed in this PR |
| F7 | Info | CSP design review | No gaps; `img-src data:` on `/docs` accepted |
| F8 | Info | Trusted Types, COOP/CORP not set | Accepted (follow-up) |
| F9 | Info | Access logs show proxy IP | Accepted |
| F10 | Info | Per-process limiter | Accepted (pre-existing) |
| F11 | Info | Auth bypass, PII, injection, secrets | No findings |
