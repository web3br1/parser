from worker_extraction.celery_app import create_celery_app


def test_create_extraction_celery_app_enables_eager_mode_without_redis(monkeypatch):
    monkeypatch.setenv("CELERY_TASK_ALWAYS_EAGER", "1")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6390/0")

    app = create_celery_app()

    assert app.conf.task_always_eager is True
    assert app.conf.task_eager_propagates is True


def test_create_extraction_celery_app_uses_dedicated_queue_and_broker_override(
    monkeypatch,
    tmp_path,
):
    broker_dir = tmp_path / "broker"
    monkeypatch.delenv("CELERY_TASK_ALWAYS_EAGER", raising=False)
    monkeypatch.setenv("CELERY_BROKER_URL", "filesystem://")
    monkeypatch.setenv("CELERY_FILESYSTEM_BROKER_DIR", str(broker_dir))

    app = create_celery_app()

    assert app.conf.broker_url == "filesystem://"
    assert app.conf.task_default_queue == "extraction"
    assert "worker_extraction.tasks" in app.conf.imports
    assert app.conf.broker_transport_options["data_folder_in"] == str(broker_dir)


def test_create_extraction_celery_app_uses_worker_runtime_env(monkeypatch):
    monkeypatch.delenv("CELERY_TASK_ALWAYS_EAGER", raising=False)
    monkeypatch.setenv("EXTRACTION_WORKER_CONCURRENCY", "1")
    monkeypatch.setenv("EXTRACTION_TASK_SOFT_TIME_LIMIT_SECONDS", "180")
    monkeypatch.setenv("EXTRACTION_TASK_TIME_LIMIT_SECONDS", "240")

    app = create_celery_app()

    assert app.conf.worker_concurrency == 1
    assert app.conf.task_soft_time_limit == 180
    assert app.conf.task_time_limit == 240
