# Build context is the repository root. cloudflare/backfill/wrangler.jsonc sets
# image_build_context so this file can see pyproject.toml and uv.lock.
#
# Storage stays on AWS S3. This image does not use Cloudflare R2.
# The fetch worker imports libipld, pyarrow, and boto3. It does not import
# pyiceberg, FastAPI, or the model packages.
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
    --group backfill

COPY lib ./lib
COPY bluesky_ingestion_jetstream ./bluesky_ingestion_jetstream
COPY bluesky_backfill_app ./bluesky_backfill_app

ENV PATH="/app/.venv/bin:${PATH}"

CMD ["python", "-m", "bluesky_backfill_app.fetch_repos.main"]
