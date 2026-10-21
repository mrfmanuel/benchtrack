#!/bin/sh
# Container entrypoint: apply migrations, then serve the API and the SPA.
# Must stay LF-only (see .gitattributes): a CR would break the shebang.
set -eu

echo "benchtrack: applying database migrations"
alembic upgrade head

echo "benchtrack: starting uvicorn on port ${PORT:-8000}"
# --proxy-headers: trust X-Forwarded-For/-Proto from the platform's reverse proxy, so the
# public rate limit keys on the real client IP.
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --proxy-headers \
    --forwarded-allow-ips='*'
