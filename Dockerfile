# BenchTrack: one image serving the API and the built SPA.
#   docker build -t benchtrack --build-arg VITE_SHOP_NAME="BenchTrack Repair" \
#     --build-arg APP_VERSION="$(git rev-parse HEAD)" .
# The image mirrors the repo layout under /app, so code that locates files relative to the
# repo root keeps working: /app/openapi.yaml (read by app/routers/docs.py) and
# /app/frontend/dist (FRONTEND_DIST).

# --- 1. Frontend build ---------------------------------------------------------------
FROM node:24-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# Baked into the bundle at build time; VITE_* values are public, never secrets.
ARG VITE_SHOP_NAME="BenchTrack Repair"
ENV VITE_SHOP_NAME=${VITE_SHOP_NAME}
# statuses.test.ts reads ../product-spec.md, but tests do not run here; the build only
# type-checks and bundles.
RUN npm run build

# --- 2. Backend dependencies (uv, from the lockfile, no dev group) --------------------
FROM python:3.12-slim AS backend
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./
RUN uv sync --locked --no-dev --no-install-project

# --- 3. Runtime ------------------------------------------------------------------------
FROM python:3.12-slim AS runtime
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FRONTEND_DIST=/app/frontend/dist \
    PORT=8000
RUN groupadd --system --gid 10001 benchtrack \
    && useradd --system --uid 10001 --gid benchtrack --no-create-home benchtrack
WORKDIR /app/backend

COPY --from=backend /app/.venv /app/.venv
COPY backend/alembic.ini ./
COPY backend/alembic/ ./alembic/
COPY backend/app/ ./app/
COPY openapi.yaml /app/openapi.yaml
COPY --from=frontend /app/frontend/dist /app/frontend/dist
COPY docker/entrypoint.sh /usr/local/bin/benchtrack-entrypoint
COPY docker/healthcheck.py /usr/local/bin/benchtrack-healthcheck

# .gitattributes keeps the script LF; strip CR anyway in case an editor added them.
# Then fail the build if the files the app reads at runtime are not where it looks.
RUN sed -i 's/\r$//' /usr/local/bin/benchtrack-entrypoint \
    && chmod 0755 /usr/local/bin/benchtrack-entrypoint \
    && python -c "from app.routers.docs import CONTRACT_PATH as c; assert c.is_file(), c" \
    && python -c "from pathlib import Path; p = Path('$FRONTEND_DIST/index.html'); assert p.is_file(), p"

# Reported by /api/health. Declared last so a new commit only rebuilds this layer. Empty
# by default: the app then falls back to RENDER_GIT_COMMIT (set by Render), then "dev".
ARG APP_VERSION=""
ENV APP_VERSION=${APP_VERSION}

USER benchtrack
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "/usr/local/bin/benchtrack-healthcheck"]
ENTRYPOINT ["/usr/local/bin/benchtrack-entrypoint"]
