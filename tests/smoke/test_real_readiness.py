from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "smoke" / "real_readiness.py"

REQUIRED_SCRIPTS = [
    Path("scripts/smoke/check_supabase_contracts.py"),
    Path("scripts/smoke/supabase_smoke.py"),
    Path("scripts/dev/check_local_stack.ps1"),
    Path("scripts/dev/start_local_stack.ps1"),
    Path("scripts/smoke/diagnose_source.py"),
    Path("scripts/smoke/cleanup_smoke.py"),
]


def load_real_readiness():
    spec = importlib.util.spec_from_file_location("real_readiness_under_test", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_ready_project(
    root: Path,
    *,
    env_overrides: dict[str, str | None] | None = None,
    migrations: list[str] | None = None,
) -> Path:
    env_values = {
        "SUPABASE_URL": "https://project-ref.supabase.co",
        "SUPABASE_ANON_KEY": "anon-key",
        "SUPABASE_SERVICE_ROLE_KEY": "service-role-key",
        "SUPABASE_DB_URL": "postgresql://postgres.example/postgres",
        "WORKSPACE_STORAGE_BUCKET": "context-builder-private",
        "REDIS_URL": "redis://localhost:6379/0",
        "SMOKE_REPORT_JSON": ".run/smoke-full.json",
    }
    for key, value in (env_overrides or {}).items():
        if value is None:
            env_values.pop(key, None)
        else:
            env_values[key] = value

    env_file = root / ".env"
    env_file.write_text(
        "\n".join(f"{key}={value}" for key, value in env_values.items()) + "\n",
        encoding="utf-8",
    )

    supabase_root = root / "supabase"
    migrations_root = supabase_root / "migrations"
    migrations_root.mkdir(parents=True)
    (supabase_root / "config.toml").write_text("project_id = \"parser\"\n", encoding="utf-8")

    for migration in migrations or ["000_extensions.sql", "001_enums.sql"]:
        (migrations_root / migration).write_text("-- migration\n", encoding="utf-8")

    for script in REQUIRED_SCRIPTS:
        script_path = root / script
        script_path.parent.mkdir(parents=True, exist_ok=True)
        script_path.write_text("# smoke helper\n", encoding="utf-8")

    return env_file


def collect_report(module, root: Path, env_file: Path):
    checks = module.collect_checks(
        root,
        env_file,
        {},
        report_json=None,
        allow_missing_redis=False,
    )
    return checks, module.build_report(checks)


def force_psql_available(module) -> None:
    module.shutil.which = lambda name: "psql" if name == "psql" else None


def render_human(module, checks) -> str:
    if hasattr(module, "render_human"):
        rendered = module.render_human(checks)
    else:
        rendered = module.render_human_report(checks)
    if isinstance(rendered, str):
        return rendered
    return "\n".join(rendered)


def render_json(module, report: dict[str, object]) -> str:
    if hasattr(module, "render_json"):
        rendered = module.render_json(report)
        return rendered if isinstance(rendered, str) else json.dumps(rendered)
    return json.dumps(report, sort_keys=True)


def test_ready_project_passes_local_readiness_checks(tmp_path: Path) -> None:
    module = load_real_readiness()
    force_psql_available(module)
    env_file = write_ready_project(tmp_path)

    _checks, report = collect_report(module, tmp_path, env_file)

    assert report["status"] == "passed"


def test_missing_env_values_fail_without_leaking_secret_values(tmp_path: Path) -> None:
    module = load_real_readiness()
    force_psql_available(module)
    sentinel = "super-secret-service-role"
    env_file = write_ready_project(
        tmp_path,
        env_overrides={
            "SUPABASE_SERVICE_ROLE_KEY": None,
            "SUPABASE_ANON_KEY": sentinel,
        },
    )

    checks, report = collect_report(module, tmp_path, env_file)
    human_output = render_human(module, checks)
    json_output = render_json(module, report)

    assert report["status"] == "failed"
    assert "SUPABASE_SERVICE_ROLE_KEY" in human_output
    assert "SUPABASE_SERVICE_ROLE_KEY" in json_output
    assert sentinel not in human_output
    assert sentinel not in json_output


def test_migration_gap_fails_and_mentions_missing_001(tmp_path: Path) -> None:
    module = load_real_readiness()
    force_psql_available(module)
    env_file = write_ready_project(
        tmp_path,
        migrations=["000_extensions.sql", "002_sources.sql"],
    )

    checks, report = collect_report(module, tmp_path, env_file)
    rendered = render_human(module, checks) + "\n" + render_json(module, report)

    assert report["status"] == "failed"
    assert "001" in rendered


def test_db_url_without_psql_or_access_token_is_not_actionable(tmp_path: Path) -> None:
    module = load_real_readiness()
    module.shutil.which = lambda _name: None
    env_file = write_ready_project(tmp_path)

    checks, report = collect_report(module, tmp_path, env_file)
    rendered = render_human(module, checks) + "\n" + render_json(module, report)

    assert report["status"] == "failed"
    assert "psql" in rendered
    assert "SUPABASE_DB_URL" in rendered


def test_configured_psql_bin_makes_db_url_actionable(tmp_path: Path) -> None:
    module = load_real_readiness()
    module.shutil.which = lambda _name: None
    psql_bin = tmp_path / "tools" / "psql.exe"
    psql_bin.parent.mkdir()
    psql_bin.write_text("fake psql\n", encoding="utf-8")
    env_file = write_ready_project(
        tmp_path,
        env_overrides={"PSQL_BIN": psql_bin.as_posix()},
    )

    _checks, report = collect_report(module, tmp_path, env_file)

    assert report["status"] == "passed"
