# syntax=docker/dockerfile:1
# Build context is the REPO ROOT (pyproject.toml lives there). In docker-compose:
#   build: { context: .., dockerfile: apps/api/Dockerfile }
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PYTHONPATH=/app/apps/api \
    PATH="/app/.venv/bin:${PATH}"

WORKDIR /app

RUN pip install --no-cache-dir uv

# Install dependencies first (cached layer). package=false ⇒ deps only, no project build.
COPY pyproject.toml ./
RUN uv sync --no-dev

# Application source, migrations, alembic config.
COPY apps/api ./apps/api
COPY migrations ./migrations
COPY alembic.ini ./

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
