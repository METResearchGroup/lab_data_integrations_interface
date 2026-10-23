# Build context is the repository root. cloudflare/backend/wrangler.jsonc sets
# image_build_context so this file can see pyproject.toml and uv.lock.
#
# Storage stays on AWS S3. This image does not use Cloudflare R2.
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Bytecode compilation keeps the first import of the API from paying that cost
# again on every cold start. The app is not installed as a package: uvicorn
# imports backend.main from PYTHONPATH, which is how Railway starts it too.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PYTHONPATH=/app \
    PORT=8000 \
    PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# backend/agentic_search imports these packages by absolute name. Copying the
# trees keeps load_env_vars.py and the AWS clients on their existing paths.
COPY backend ./backend
COPY lib ./lib
COPY bluesky_ingestion_jetstream ./bluesky_ingestion_jetstream
COPY ml_tooling ./ml_tooling
# Jetstream and the backfill worker reuse this image and replace CMD at start.
COPY bluesky_backfill_app ./bluesky_backfill_app

ENV PATH="/app/.venv/bin:${PATH}"

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
