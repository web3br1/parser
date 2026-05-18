import os
from pathlib import Path

from celery import Celery


def _broker_url(eager: bool) -> str:
    if eager:
        return "memory://"
    return str(os.getenv("CELERY_BROKER_URL") or os.getenv("REDIS_URL", "redis://localhost:6379/0"))


def _backend_url(eager: bool, broker_url: str) -> str:
    if eager:
        return "cache+memory://"
    return os.getenv("CELERY_RESULT_BACKEND") or (
        "cache+memory://" if broker_url.startswith("filesystem://") else broker_url
    )


def _filesystem_transport_options(broker_url: str) -> dict[str, str]:
    if not broker_url.startswith("filesystem://"):
        return {}
    broker_dir = Path(os.getenv("CELERY_FILESYSTEM_BROKER_DIR", ".run/celery/broker"))
    processed_dir = Path(
        os.getenv("CELERY_FILESYSTEM_PROCESSED_DIR", ".run/celery/processed")
    )
    broker_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)
    return {
        "data_folder_in": str(broker_dir),
        "data_folder_out": str(broker_dir),
        "processed_folder": str(processed_dir),
    }


def create_celery_app() -> Celery:
    eager = os.getenv("CELERY_TASK_ALWAYS_EAGER") == "1"
    broker_url = _broker_url(eager)
    backend_url = _backend_url(eager, broker_url)
    app = Celery("worker_extraction", broker=broker_url, backend=backend_url)
    app.conf.update(
        task_default_queue="extraction",
        imports=("worker_extraction.tasks",),
        broker_transport_options=_filesystem_transport_options(broker_url),
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        task_soft_time_limit=60,
        task_time_limit=90,
        task_always_eager=eager,
        task_eager_propagates=eager,
    )
    return app


app = create_celery_app()
