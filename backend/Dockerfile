FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY backend/ ./backend/

EXPOSE 8080

CMD [".venv/bin/uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8080"]