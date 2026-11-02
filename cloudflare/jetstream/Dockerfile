# Build context is the repository root. cloudflare/jetstream/wrangler.jsonc sets
# image_build_context so this file can see pyproject.toml and uv.lock.
#
# Storage stays on AWS S3. This image does not use Cloudflare R2.
# Sync the ingestion group only. The API image adds the api and ml groups.
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-default-groups --no-install-project \
    --group ingestion

COPY lib ./lib
COPY bluesky_ingestion_jetstream ./bluesky_ingestion_jetstream

ENV PATH="/app/.venv/bin:${PATH}"

CMD ["python", "-m", "bluesky_ingestion_jetstream.main"]
