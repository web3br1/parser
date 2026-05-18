import os

from celery import Celery


def create_celery_app() -> Celery:
    broker_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    return Celery("worker_review", broker=broker_url, backend=broker_url)


app = create_celery_app()
