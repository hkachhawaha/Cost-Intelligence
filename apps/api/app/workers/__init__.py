"""Celery application factory.

Declares queues for the future agent pipeline (ingestion/matching/detection) and
sets fair-dispatch + late-ack defaults for natural back-pressure. OTel
instrumentation attaches per worker process when an OTLP endpoint is configured.
"""

from __future__ import annotations

from celery import Celery
from celery.signals import worker_process_init

from app.core.config import settings

celery = Celery(
    "terzo",
    broker=str(settings.redis_url),
    backend=str(settings.redis_url),
)
celery.conf.update(
    task_default_queue="default",
    task_routes={
        "app.workers.ingestion_tasks.*": {"queue": "ingestion"},
        "app.workers.matching_tasks.*": {"queue": "matching"},
        "app.workers.detection_tasks.*": {"queue": "detection"},
    },
    task_acks_late=True,  # redeliver if a worker dies mid-task
    worker_prefetch_multiplier=1,  # fair dispatch; back-pressure friendly
    task_track_started=True,
)


@worker_process_init.connect
def _init_otel(**_kwargs):
    if settings.otel_exporter_otlp_endpoint:
        from opentelemetry.instrumentation.celery import CeleryInstrumentor

        CeleryInstrumentor().instrument()
