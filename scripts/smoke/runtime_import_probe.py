from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

SMOKE_DIR = Path(__file__).resolve().parent
if str(SMOKE_DIR) not in sys.path:
    sys.path.insert(0, str(SMOKE_DIR))

from run_real_smoke import sanitize_text, tail  # noqa: E402

DEFAULT_BUNDLE_PATH = (
    r"C:\tmp\context-builder-sources\compounding-pharmacy-gold"
    r"\compounding-pharmacy-gold.context_bundle.v1.json"
)
COMMAND_ENV = "CONTEXT_BUNDLE_RUNTIME_IMPORT_COMMAND"


@dataclass
class RuntimeImportReport:
    status: str
    started_at: str
    finished_at: str
    command: list[str]
    bundle_path: str
    returncode: int | None
    duration_seconds: float
    stdout_tail: str
    stderr_tail: str
    error: str | None


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def split_command(command: str) -> list[str]:
    parts = shlex.split(command, posix=os.name != "nt")
    if os.name == "nt":
        return [part[1:-1] if len(part) >= 2 and part[0] == part[-1] == '"' else part for part in parts]
    return parts


def render_command(command_template: str, bundle_path: str) -> list[str]:
    return [part.replace("{bundle}", bundle_path) for part in split_command(command_template)]


def ensure_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def command_from_args(args: argparse.Namespace, env: Mapping[str, str]) -> str | None:
    return args.command or env.get(COMMAND_ENV)


def failed_config_report(
    args: argparse.Namespace,
    started_at: str,
    started: float,
    error: str,
) -> RuntimeImportReport:
    return RuntimeImportReport(
        status="failed",
        started_at=started_at,
        finished_at=utc_now(),
        command=[],
        bundle_path=args.bundle_path,
        returncode=None,
        duration_seconds=round(time.perf_counter() - started, 3),
        stdout_tail="",
        stderr_tail="",
        error=error,
    )


def write_report(path: str, report: RuntimeImportReport, env: Mapping[str, str]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(asdict(report), indent=2, sort_keys=True)
    target.write_text(sanitize_text(serialized, env), encoding="utf-8")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe runtime import of a context_bundle.v1 file.")
    parser.add_argument("--bundle-path", default=DEFAULT_BUNDLE_PATH)
    parser.add_argument("--command", default=None)
    parser.add_argument("--json-report", default=None)
    parser.add_argument("--timeout-seconds", type=float, default=900.0)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    env = os.environ.copy()
    started_at = utc_now()
    started = time.perf_counter()
    command_template = command_from_args(args, env)

    if not command_template:
        report = failed_config_report(args, started_at, started, "runtime_import_command_required")
        print("ERROR: runtime import command required", file=sys.stderr)
        if args.json_report:
            write_report(args.json_report, report, env)
        return 2

    try:
        command = render_command(command_template, args.bundle_path)
    except ValueError:
        report = failed_config_report(args, started_at, started, "runtime_import_command_invalid")
        print("ERROR: runtime import command invalid", file=sys.stderr)
        if args.json_report:
            write_report(args.json_report, report, env)
        return 2

    if not command:
        report = failed_config_report(args, started_at, started, "runtime_import_command_invalid")
        print("ERROR: runtime import command invalid", file=sys.stderr)
        if args.json_report:
            write_report(args.json_report, report, env)
        return 2

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            shell=False,
            timeout=args.timeout_seconds,
        )
        duration = time.perf_counter() - started
        status = "passed" if completed.returncode == 0 else "failed"
        report = RuntimeImportReport(
            status=status,
            started_at=started_at,
            finished_at=utc_now(),
            command=[sanitize_text(part, env) for part in command],
            bundle_path=sanitize_text(args.bundle_path, env),
            returncode=completed.returncode,
            duration_seconds=round(duration, 3),
            stdout_tail=sanitize_text(tail(ensure_text(completed.stdout)), env),
            stderr_tail=sanitize_text(tail(ensure_text(completed.stderr)), env),
            error=None,
        )
    except subprocess.TimeoutExpired as exc:
        duration = time.perf_counter() - started
        report = RuntimeImportReport(
            status="failed",
            started_at=started_at,
            finished_at=utc_now(),
            command=[sanitize_text(part, env) for part in command],
            bundle_path=sanitize_text(args.bundle_path, env),
            returncode=None,
            duration_seconds=round(duration, 3),
            stdout_tail=sanitize_text(tail(ensure_text(exc.stdout)), env),
            stderr_tail=sanitize_text(tail(ensure_text(exc.stderr)), env),
            error=f"Timed out after {args.timeout_seconds:g}s",
        )

    if args.json_report:
        write_report(args.json_report, report, env)

    if report.status == "passed":
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
