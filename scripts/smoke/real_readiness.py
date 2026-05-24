"""Local readiness gate for real Supabase smoke runs.

This script intentionally performs filesystem and environment checks only. It
does not start services, run subprocesses, or contact Supabase.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

Status = Literal["ok", "warn", "fail"]

REQUIRED_ENV_VARS = (
    "SUPABASE_URL",
    "SUPABASE_ANON_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
)
DIRECT_SQL_VARS = ("SUPABASE_DB_URL", "DATABASE_URL")
POOLER_SQL_VARS = (
    "SUPABASE_POOLER_DB_URL",
    "SUPABASE_IPV4_DB_URL",
    "DATABASE_POOLER_URL",
)
PSQL_BIN_VARS = ("PSQL_BIN", "SUPABASE_PSQL_BIN")
REQUIRED_BUCKET = "context-builder-private"
REQUIRED_SCRIPTS = (
    "scripts/smoke/check_supabase_contracts.py",
    "scripts/smoke/supabase_smoke.py",
    "scripts/smoke/diagnose_source.py",
    "scripts/smoke/cleanup_smoke.py",
    "scripts/ops/storage_gc.py",
)
MIGRATION_RE = re.compile(r"^(\d{3})_.*\.sql$")


@dataclass(frozen=True)
class Check:
    name: str
    status: Status
    message: str
    details: dict[str, object]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _relative_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return os.path.relpath(path, root).replace(os.sep, "/")


def _has_value(env: Mapping[str, str], name: str) -> bool:
    return bool(env.get(name, "").strip())


def _project_ref_from_url(value: str) -> bool:
    parsed = urlparse(value)
    host = parsed.netloc
    if not host.endswith(".supabase.co"):
        return False
    project_ref = host[: -len(".supabase.co")]
    return bool(project_ref and "." not in project_ref)


def _configured_psql(env: Mapping[str, str]) -> tuple[bool, str]:
    for name in PSQL_BIN_VARS:
        value = env.get(name, "").strip()
        if value and Path(value).exists():
            return True, name
    if shutil.which("psql"):
        return True, "PATH"
    return False, ""


def load_env_file(path: Path) -> dict[str, str]:
    """Load a dotenv-style file without expanding variables or leaking values."""

    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        if "=" not in line:
            continue

        name, raw_value = line.split("=", 1)
        name = name.strip()
        if not name:
            continue

        value = raw_value.strip()
        try:
            parts = shlex.split(value, comments=True, posix=True)
        except ValueError:
            parts = [value.strip("\"'")]
        values[name] = parts[0] if len(parts) == 1 else " ".join(parts)

    return values


def merged_env(env_file: Path, environ: Mapping[str, str]) -> dict[str, str]:
    values = load_env_file(env_file)
    values.update(environ)
    return values


def _check_env_file(root: Path, env_file: Path) -> Check:
    rel_path = _relative_path(env_file, root)
    if env_file.exists():
        return Check(
            "env_file",
            "ok",
            f"Env file exists: {rel_path}",
            {"path": rel_path},
        )
    return Check(
        "env_file",
        "fail",
        f"Env file is missing: {rel_path}",
        {"path": rel_path},
    )


def _check_required_env(env: Mapping[str, str]) -> Check:
    missing = [name for name in REQUIRED_ENV_VARS if not _has_value(env, name)]
    if not missing:
        return Check(
            "required_env",
            "ok",
            "Required Supabase variables are present",
            {"variables": list(REQUIRED_ENV_VARS), "count": len(REQUIRED_ENV_VARS)},
        )
    return Check(
        "required_env",
        "fail",
        "Missing required Supabase variables: " + ", ".join(missing),
        {"missing": missing, "required": list(REQUIRED_ENV_VARS)},
    )


def _check_sql_access(env: Mapping[str, str]) -> Check:
    has_psql, psql_source = _configured_psql(env)
    direct = [name for name in DIRECT_SQL_VARS if _has_value(env, name)]
    if direct and has_psql:
        return Check(
            "sql_access",
            "ok",
            "SQL access can use a direct database URL",
            {"mode": "direct", "variables": direct, "psql_source": psql_source},
        )

    pooler = [name for name in POOLER_SQL_VARS if _has_value(env, name)]
    if pooler and has_psql:
        return Check(
            "sql_access",
            "ok",
            "SQL access can use a pooler database URL",
            {"mode": "pooler", "variables": pooler, "psql_source": psql_source},
        )

    has_project_ref = _has_value(env, "SUPABASE_PROJECT_REF") or _project_ref_from_url(
        env.get("SUPABASE_URL", "")
    )
    if _has_value(env, "SUPABASE_ACCESS_TOKEN") and has_project_ref:
        project_source = (
            "SUPABASE_PROJECT_REF"
            if _has_value(env, "SUPABASE_PROJECT_REF")
            else "SUPABASE_URL"
        )
        return Check(
            "sql_access",
            "ok",
            "SQL access can use a Supabase access token with project ref",
            {
                "mode": "access_token",
                "variables": ["SUPABASE_ACCESS_TOKEN", project_source],
            },
        )

    return Check(
        "sql_access",
        "fail",
        "No SQL access path found; set psql on PATH or PSQL_BIN with a database URL, or set access token with project ref",
        {
            "accepted_variable_groups": [
                [*DIRECT_SQL_VARS, "psql"],
                [*POOLER_SQL_VARS, "psql"],
                [*DIRECT_SQL_VARS, *PSQL_BIN_VARS],
                [*POOLER_SQL_VARS, *PSQL_BIN_VARS],
                ["SUPABASE_ACCESS_TOKEN", "SUPABASE_PROJECT_REF"],
                ["SUPABASE_ACCESS_TOKEN", "SUPABASE_URL"],
            ],
            "db_url_present": bool(direct or pooler),
            "psql_available": has_psql,
            "psql_bin_variables": list(PSQL_BIN_VARS),
        },
    )


def _check_bucket(env: Mapping[str, str]) -> Check:
    name = "WORKSPACE_STORAGE_BUCKET"
    if env.get(name, "").strip() == REQUIRED_BUCKET:
        return Check(
            "storage_bucket",
            "ok",
            f"{name} resolves to the required bucket",
            {"variable": name, "required": REQUIRED_BUCKET},
        )
    return Check(
        "storage_bucket",
        "fail",
        f"{name} must resolve to {REQUIRED_BUCKET}",
        {"variable": name, "required": REQUIRED_BUCKET},
    )


def _check_redis(env: Mapping[str, str], allow_missing_redis: bool) -> Check:
    name = "REDIS_URL"
    if _has_value(env, name):
        return Check("redis", "ok", f"{name} is present", {"variable": name})
    if allow_missing_redis:
        return Check(
            "redis",
            "warn",
            f"{name} is missing but allowed by flag",
            {"variable": name, "allowed_by_flag": True},
        )
    return Check("redis", "fail", f"{name} is missing", {"variable": name})


def _check_report_json(env: Mapping[str, str], report_json: str | None) -> Check:
    name = "SMOKE_REPORT_JSON"
    if report_json and report_json.strip():
        return Check(
            "report_json",
            "ok",
            "Smoke report JSON path provided by CLI flag",
            {"source": "cli", "variable": name},
        )
    if _has_value(env, name):
        return Check(
            "report_json",
            "ok",
            f"{name} is present",
            {"source": "environment", "variable": name},
        )
    return Check(
        "report_json",
        "warn",
        f"{name} is missing and no --report-json path was provided",
        {"variable": name, "flag": "--report-json"},
    )


def _check_supabase_config(root: Path) -> Check:
    path = root / "supabase" / "config.toml"
    rel_path = _relative_path(path, root)
    if path.exists():
        return Check(
            "supabase_config",
            "ok",
            f"Supabase config exists: {rel_path}",
            {"path": rel_path},
        )
    return Check(
        "supabase_config",
        "fail",
        f"Supabase config is missing: {rel_path}",
        {"path": rel_path},
    )


def _check_migrations(root: Path) -> Check:
    migrations_dir = root / "supabase" / "migrations"
    files = sorted(migrations_dir.glob("*.sql")) if migrations_dir.exists() else []
    numbers = sorted(
        {
            int(match.group(1))
            for path in files
            if (match := MIGRATION_RE.match(path.name)) is not None
        }
    )

    if not numbers:
        return Check(
            "migrations",
            "fail",
            "No numbered Supabase migrations found",
            {"path": "supabase/migrations", "count": 0},
        )

    highest = numbers[-1]
    expected = set(range(0, highest + 1))
    missing = sorted(expected.difference(numbers))
    details = {
        "path": "supabase/migrations",
        "count": len(numbers),
        "highest": f"{highest:03d}",
    }
    if missing:
        missing_text = [f"{number:03d}" for number in missing]
        return Check(
            "migrations",
            "fail",
            "Supabase migration sequence has gaps: " + ", ".join(missing_text),
            {**details, "missing": missing_text},
        )

    return Check(
        "migrations",
        "ok",
        f"Supabase migrations are contiguous from 000 through {highest:03d}",
        details,
    )


def _check_required_scripts(root: Path) -> Check:
    missing = [path for path in REQUIRED_SCRIPTS if not (root / path).exists()]
    if missing:
        return Check(
            "required_scripts",
            "fail",
            "Required real-test scripts are missing: " + ", ".join(missing),
            {"missing": missing, "required": list(REQUIRED_SCRIPTS)},
        )
    return Check(
        "required_scripts",
        "ok",
        "Required real-test scripts exist",
        {"required": list(REQUIRED_SCRIPTS), "count": len(REQUIRED_SCRIPTS)},
    )


def collect_checks(
    root: Path,
    env_file: Path,
    environ: Mapping[str, str],
    *,
    report_json: str | None,
    allow_missing_redis: bool,
    psql_bin: str | None = None,
) -> list[Check]:
    root = root.resolve()
    env_file = env_file if env_file.is_absolute() else root / env_file
    env = merged_env(env_file, environ)
    if psql_bin:
        env["PSQL_BIN"] = psql_bin

    return [
        _check_env_file(root, env_file),
        _check_required_env(env),
        _check_sql_access(env),
        _check_bucket(env),
        _check_redis(env, allow_missing_redis),
        _check_report_json(env, report_json),
        _check_supabase_config(root),
        _check_migrations(root),
        _check_required_scripts(root),
    ]


def build_report(checks: Sequence[Check]) -> dict[str, object]:
    counts = {"ok": 0, "warn": 0, "fail": 0}
    for check in checks:
        counts[check.status] += 1

    return {
        "status": "failed" if counts["fail"] else "passed",
        "checks": [asdict(check) for check in checks],
        "summary": {
            "ok": counts["ok"],
            "warn": counts["warn"],
            "fail": counts["fail"],
            "total": len(checks),
        },
    }


def render_human(checks: Sequence[Check]) -> str:
    lines = [f"{check.status.upper():4} {check.name}: {check.message}" for check in checks]
    report = build_report(checks)
    summary = report["summary"]
    if isinstance(summary, dict):
        lines.append(
            "SUMMARY "
            f"status={report['status']} "
            f"ok={summary['ok']} warn={summary['warn']} fail={summary['fail']}"
        )
    return "\n".join(lines)


def render_json(report: Mapping[str, object]) -> str:
    return json.dumps(report, indent=2, sort_keys=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check local readiness for real Supabase smoke tests."
    )
    parser.add_argument("--env-file", default=None, help="Path to dotenv file")
    parser.add_argument("--json", action="store_true", help="Print JSON report")
    parser.add_argument(
        "--report-json",
        default=None,
        help="Smoke run JSON report path to require for downstream smoke command",
    )
    parser.add_argument(
        "--allow-missing-redis",
        action="store_true",
        help="Warn instead of failing when REDIS_URL is absent",
    )
    parser.add_argument(
        "--psql-bin",
        default=None,
        help="Path to psql executable when it is not on PATH",
    )
    args = parser.parse_args(argv)

    root = _repo_root()
    env_file = Path(args.env_file) if args.env_file else root / ".env"
    checks = collect_checks(
        root,
        env_file,
        os.environ,
        report_json=args.report_json,
        allow_missing_redis=args.allow_missing_redis,
        psql_bin=args.psql_bin,
    )

    report = build_report(checks)
    if args.json:
        print(render_json(report))
    else:
        print(render_human(checks))

    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
