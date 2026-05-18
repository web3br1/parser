from worker_ingest.celery_app import create_celery_app


def test_create_celery_app_enables_eager_mode_without_redis(monkeypatch):
    monkeypatch.setenv("CELERY_TASK_ALWAYS_EAGER", "1")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6390/0")

    app = create_celery_app()

    assert app.conf.task_always_eager is True
    assert app.conf.task_eager_propagates is True


def test_create_ingest_celery_app_uses_dedicated_queue_and_broker_override(monkeypatch, tmp_path):
    broker_dir = tmp_path / "broker"
    processed_dir = tmp_path / "processed"
    monkeypatch.delenv("CELERY_TASK_ALWAYS_EAGER", raising=False)
    monkeypatch.setenv("CELERY_BROKER_URL", "filesystem://")
    monkeypatch.setenv("CELERY_FILESYSTEM_BROKER_DIR", str(broker_dir))
    monkeypatch.setenv("CELERY_FILESYSTEM_PROCESSED_DIR", str(processed_dir))

    app = create_celery_app()

    assert app.conf.broker_url == "filesystem://"
    assert app.conf.task_default_queue == "ingest"
    assert "worker_ingest.tasks" in app.conf.imports
    assert app.conf.broker_transport_options["data_folder_in"] == str(broker_dir)
    assert app.conf.broker_transport_options["data_folder_out"] == str(broker_dir)
