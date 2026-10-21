#!/bin/sh
# Container entrypoint: apply migrations, then serve the API and the SPA.
# Must stay LF-only (see .gitattributes): a CR would break the shebang.
set -eu

echo "benchtrack: applying database migrations"
alembic upgrade head

echo "benchtrack: starting uvicorn on port ${PORT:-8000}"
# --no-proxy-headers: do not let uvicorn rewrite the client address from X-Forwarded-For.
# With --forwarded-allow-ips='*' it used the leftmost entry, which the client controls
# (Render appends to it), so anyone could dodge the public rate limit with a fake IP. The app
# reads the client IP from CLIENT_IP_HEADER instead, and HTTPS from X-Forwarded-Proto
# (app/services/client_ip.py, app/security_headers.py).
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --no-proxy-headers
