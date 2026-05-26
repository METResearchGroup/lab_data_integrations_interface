FROM python:3.11-slim

# uv 0.11.16
COPY --from=ghcr.io/astral-sh/uv@sha256:440fd6477af86a2f1b38080c539f1672cd22acb1b1a47e321dba5158ab08864d /uv /usr/local/bin/uv

WORKDIR /app
RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app

COPY --chown=appuser:appuser pyproject.toml uv.lock ./
USER appuser
RUN uv sync --frozen --no-dev

COPY --chown=appuser:appuser backend/ ./backend/

EXPOSE 8080

CMD [".venv/bin/uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8080"]
