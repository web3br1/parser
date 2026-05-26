from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import httpx

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_API_BASE_URL = "http://localhost:8000"
TAIL_CHARS = 4000

PhaseKind = Literal["subprocess", "health"]
PhaseStatus = Literal["passed", "failed", "planned", "skipped"]

SECRET_NAME_RE = re.compile(
    r"(KEY|TOKEN|SECRET|PASSWORD|PASS|DATABASE_URL|DB_URL|MODEL|OPENAI|"
    r"ANTHROPIC|SUPABASE|POSTGRES|JWT)",
    re.IGNORECASE,
)
SECRET_VALUE_PATTERNS = (
    re.compile(r"postgres(?:ql)?://[^\s\"']+", re.IGNORECASE),
    re.compile(r"postgresql\+asyncpg://[^\s\"']+", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
    re.compile(r"\b(?:eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,})\b"),
    re.compile(r"\b(?:sb|sk|pk|rk|org|proj)-[A-Za-z0-9_-]{16,}\b", re.IGNORECASE),
)


@dataclass(frozen=True)
class Phase:
    name: str
    kind: PhaseKind
    command: list[str]
    timeout_seconds: float = 600.0
    env_overrides: dict[str, str] = field(default_factory=dict)


@dataclass
class PhaseResult:
    name: str
    status: PhaseStatus
    command: list[str]
    returncode: int | None
    duration_seconds: float
    stdout_tail: str = ""
    stderr_tail: str = ""
    error: str | None = None


@dataclass
class RunReport:
    target: str
    mode: str
    status: str
    started_at: str
    finished_at: str | None = None
    phases: list[PhaseResult] = field(default_factory=list)


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _secret_values(env: Mapping[str, str]) -> list[str]:
    values: list[str] = []
    for name, value in env.items():
        if not value or len(value) < 4:
            continue
        if SECRET_NAME_RE.search(name):
            values.append(value)
    return sorted(values, key=len, reverse=True)


def sanitize_text(text: str, env: Mapping[str, str]) -> str:
    sanitized = text
    for value in _secret_values(env):
        sanitized = sanitized.replace(value, "[REDACTED]")
    for pattern in SECRET_VALUE_PATTERNS:
        sanitized = pattern.sub("[REDACTED]", sanitized)
    return sanitized


def tail(text: str) -> str:
    return text[-TAIL_CHARS:] if len(text) > TAIL_CHARS else text


def python_cmd(script: str, *args: str) -> list[str]:
    return [sys.executable, script, *args]


def api_base_url(args: argparse.Namespace, env: Mapping[str, str]) -> str:
    value = args.api_base_url or env.get("API_BASE_URL") or DEFAULT_API_BASE_URL
    return value.rstrip("/")


def smoke_report_path(json_report: str | None, name: str) -> str | None:
    if not json_report:
        return None
    path = Path(json_report)
    suffix = path.suffix or ".json"
    return str(path.with_name(f"{path.stem}-{name}{suffix}"))


def build_phases(args: argparse.Namespace, env: Mapping[str, str]) -> list[Phase]:
    base_url = api_base_url(args, env)
    common_env = {"API_BASE_URL": base_url}

    phases = []
    if not args.skip_readiness:
        phases.append(
            Phase(
                "readiness",
                "subprocess",
                python_cmd("scripts/smoke/real_readiness.py"),
                env_overrides=common_env,
            )
        )
    if not args.skip_contracts:
        phases.append(
            Phase(
                "contracts",
                "subprocess",
                python_cmd("scripts/smoke/check_supabase_contracts.py"),
                timeout_seconds=900.0,
                env_overrides=common_env,
            )
        )

    min_report = smoke_report_path(args.json_report, "smoke-min")
    full_report = smoke_report_path(args.json_report, "smoke-full")
    min_command = python_cmd("scripts/smoke/supabase_smoke.py")
    if min_report:
        min_command.extend(["--json-report", min_report])

    phases.extend(
        [
            Phase("health", "health", ["GET", f"{base_url}/health"], env_overrides=common_env),
            Phase(
                "smoke-min",
                "subprocess",
                min_command,
                timeout_seconds=1200.0,
                env_overrides=common_env,
            ),
        ]
    )

    if args.full:
        full_command = python_cmd("scripts/smoke/supabase_smoke.py", "--full")
        if full_report:
            full_command.extend(["--json-report", full_report])
        phases.append(
            Phase(
                "smoke-full",
                "subprocess",
                full_command,
                timeout_seconds=1800.0,
                env_overrides=common_env,
            )
        )
        if not args.skip_source_pack_compile:
            phases.append(
                Phase(
                    "source-pack-compile",
                    "subprocess",
                    python_cmd(
                        "scripts/source_pack/compile_context_bundle.py",
                        "--source-dir",
                        args.source_pack_dir,
                        "--check",
                    ),
                    env_overrides=common_env,
                )
            )
        if not args.skip_runtime_import:
            phases.append(
                Phase(
                    "runtime-import",
                    "subprocess",
                    python_cmd("scripts/smoke/runtime_import_probe.py"),
                    env_overrides=common_env,
                )
            )

    return phases


def run_subprocess_phase(phase: Phase, env: Mapping[str, str]) -> PhaseResult:
    started = time.perf_counter()
    process_env = os.environ.copy()
    process_env.update(phase.env_overrides)
    try:
        completed = subprocess.run(
            phase.command,
            cwd=ROOT,
            env=process_env,
            text=True,
            capture_output=True,
            timeout=phase.timeout_seconds,
            check=False,
        )
        duration = time.perf_counter() - started
        status: PhaseStatus = "passed" if completed.returncode == 0 else "failed"
        return PhaseResult(
            name=phase.name,
            status=status,
            command=[sanitize_text(part, env) for part in phase.command],
            returncode=completed.returncode,
            duration_seconds=round(duration, 3),
            stdout_tail=sanitize_text(tail(completed.stdout or ""), env),
            stderr_tail=sanitize_text(tail(completed.stderr or ""), env),
        )
    except subprocess.TimeoutExpired as exc:
        duration = time.perf_counter() - started
        return PhaseResult(
            name=phase.name,
            status="failed",
            command=[sanitize_text(part, env) for part in phase.command],
            returncode=None,
            duration_seconds=round(duration, 3),
            stdout_tail=sanitize_text(tail(exc.stdout or ""), env),
            stderr_tail=sanitize_text(tail(exc.stderr or ""), env),
            error=f"Timed out after {phase.timeout_seconds:g}s",
        )


def run_health_phase(phase: Phase, env: Mapping[str, str]) -> PhaseResult:
    started = time.perf_counter()
    url = phase.command[1]
    try:
        response = httpx.get(url, timeout=30.0)
        duration = time.perf_counter() - started
        stdout = f"HTTP {response.status_code}"
        stderr = "" if response.status_code == 200 else response.text
        return PhaseResult(
            name=phase.name,
            status="passed" if response.status_code == 200 else "failed",
            command=[sanitize_text(part, env) for part in phase.command],
            returncode=0 if response.status_code == 200 else response.status_code,
            duration_seconds=round(duration, 3),
            stdout_tail=sanitize_text(tail(stdout), env),
            stderr_tail=sanitize_text(tail(stderr), env),
        )
    except httpx.HTTPError as exc:
        duration = time.perf_counter() - started
        return PhaseResult(
            name=phase.name,
            status="failed",
            command=[sanitize_text(part, env) for part in phase.command],
            returncode=None,
            duration_seconds=round(duration, 3),
            error=sanitize_text(str(exc), env),
        )


def run_phase(phase: Phase, env: Mapping[str, str]) -> PhaseResult:
    if phase.kind == "health":
        return run_health_phase(phase, env)
    return run_subprocess_phase(phase, env)


def dry_run_result(phase: Phase, env: Mapping[str, str]) -> PhaseResult:
    return PhaseResult(
        name=phase.name,
        status="planned",
        command=[sanitize_text(part, env) for part in phase.command],
        returncode=None,
        duration_seconds=0.0,
    )


def write_report(path: str, report: RunReport, env: Mapping[str, str]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = asdict(report)
    serialized = json.dumps(data, indent=2, sort_keys=True)
    target.write_text(sanitize_text(serialized, env), encoding="utf-8")


def print_phase_result(result: PhaseResult) -> None:
    print(f"[{result.status.upper()}] {result.name} ({result.duration_seconds:.3f}s)")
    if result.status == "failed":
        print(f"  command: {' '.join(result.command)}")
        if result.error:
            print(f"  error: {result.error}")


def validate_args(args: argparse.Namespace, env: Mapping[str, str]) -> str | None:
    if args.target == "cloud" and not (args.api_base_url or env.get("API_BASE_URL")):
        return "--target cloud requires --api-base-url or API_BASE_URL"
    return None


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run real smoke validation phases.")
    parser.add_argument("--target", choices=("local", "cloud"), default="local")
    parser.add_argument("--full", action="store_true", help="Run full smoke after minimum smoke.")
    parser.add_argument("--json-report", default=None, help="Write orchestration JSON report.")
    parser.add_argument("--api-base-url", default=None, help="Override API_BASE_URL.")
    parser.add_argument(
        "--source-pack-dir",
        default=r"C:\tmp\context-builder-sources\compounding-pharmacy-gold",
        help="Source pack directory checked during full smoke.",
    )
    parser.add_argument("--skip-readiness", action="store_true", help="Skip local readiness phase.")
    parser.add_argument("--skip-contracts", action="store_true", help="Skip Supabase contract phase.")
    parser.add_argument(
        "--skip-source-pack-compile",
        action="store_true",
        help="Skip source pack compile check during full smoke.",
    )
    parser.add_argument(
        "--skip-runtime-import",
        action="store_true",
        help="Skip runtime import probe during full smoke.",
    )
    parser.add_argument("--continue-on-failure", action="store_true", help="Run later phases after failures.")
    parser.add_argument("--dry-run", action="store_true", help="Plan phases without subprocesses or HTTP.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    env = os.environ.copy()

    validation_error = validate_args(args, env)
    env["API_BASE_URL"] = api_base_url(args, env)
    started_at = utc_now()
    report = RunReport(
        target=args.target,
        mode="full" if args.full else "minimal",
        status="running",
        started_at=started_at,
    )

    if validation_error:
        report.status = "failed"
        report.finished_at = utc_now()
        print(f"ERROR: {validation_error}", file=sys.stderr)
        if args.json_report:
            write_report(args.json_report, report, env)
        return 2

    phases = build_phases(args, env)
    if args.dry_run:
        for phase in phases:
            result = dry_run_result(phase, env)
            report.phases.append(result)
            print_phase_result(result)
        report.status = "planned"
        report.finished_at = utc_now()
        if args.json_report:
            write_report(args.json_report, report, env)
        return 0

    failed = False
    for phase in phases:
        result = run_phase(phase, env)
        report.phases.append(result)
        print_phase_result(result)
        if result.status == "failed":
            failed = True
            if not args.continue_on_failure:
                break

    report.status = "failed" if failed else "passed"
    report.finished_at = utc_now()
    if args.json_report:
        write_report(args.json_report, report, env)

    if failed:
        failing = next((phase for phase in report.phases if phase.status == "failed"), None)
        if failing:
            print(f"First failing phase: {failing.name}", file=sys.stderr)
            print(f"Next suggested command: {' '.join(failing.command)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
