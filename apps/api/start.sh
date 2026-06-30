#!/bin/bash

# Apply database migrations
echo "Applying database migrations..."
alembic upgrade head

# Start Celery worker in the background
echo "Starting Celery worker..."
celery -A app.workers.ingestion_tasks worker --loglevel=info &

# Start FastAPI API in the foreground (PID 1)
echo "Starting FastAPI application..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
