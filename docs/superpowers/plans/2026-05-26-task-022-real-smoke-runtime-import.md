# TASK-022 Real Smoke Runtime Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove the Context Compiler end to end against real Docker/Supabase and a consumer runtime importing `context_bundle.v1` without manual edits.

**Architecture:** Extend the existing real smoke orchestrator instead of creating a second smoke path. Keep Docker/Supabase validation, source-pack compilation, runtime import proof, deterministic hash proof, and sanitized JSON reports as explicit phases in one auditable run.

**Tech Stack:** Python 3.12, pytest, FastAPI smoke scripts, Supabase CLI/Docker runtime, `packages/source_pack`, existing `scripts/smoke/run_real_smoke.py`, existing `scripts/source_pack/compile_context_bundle.py`.

---

## Agent Model

Each agent has exactly one function:

- **Agent 1 - Smoke Contract Implementer:** Owns smoke orchestrator contract, args, report metadata, and tests.
- **Agent 2 - Source Pack Proof Implementer:** Owns source-pack compile/hash proof script behavior and tests.
- **Agent 3 - Runtime Import Adapter Implementer:** Owns configurable external runtime import command wrapper and tests.
- **Agent 4 - Documentation/Runbook Implementer:** Owns `TASK-022` and operations docs only.
- **Agent 5 - Spec Reviewer:** Read-only reviewer for acceptance coverage.
- **Agent 6 - Quality/Security Reviewer:** Read-only reviewer for robustness, secret redaction, path leakage, and destructive-command risk.

Controller rule: do not dispatch implementation agents in parallel if their write sets overlap. Review happens after each implementation task: spec review first, quality review second.

## File Map

- Modify: `scripts/smoke/run_real_smoke.py`
  - Adds source-pack compile phase, runtime import phase, report metadata, and stronger validation.
- Modify: `tests/smoke/test_real_smoke_orchestrator.py`
  - Tests phase order, report metadata, redaction, hash proof command, and runtime import command behavior.
- Create: `scripts/smoke/runtime_import_probe.py`
  - Runs an allowlisted external command from env/CLI, records sanitized result, and fails clearly when no runtime command is configured.
- Create: `tests/smoke/test_runtime_import_probe.py`
  - Covers missing config, successful command, failed command, timeout, and secret redaction.
- Modify: `tasks/TASK-022-real-smoke-runtime-import.md`
  - Tracks implementation status and exact verified commands.
- Modify: `docs/operations/smoke-runbook.md`
  - Updates migrations through `047`, Context Build staging, runtime import proof, and report location.

## Non-Negotiables

- No destructive cleanup in TASK-022.
- No raw secrets in stdout, stderr, JSON reports, docs, or task files.
- The orchestrator must not start or stop the stack; it validates an already-running runtime.
- Runtime import command must be explicit via CLI/env. If absent, the phase must fail or be skipped only when a deliberate `--skip-runtime-import` flag is passed.
- Source-pack compile proof must use `C:\tmp\context-builder-sources\compounding-pharmacy-gold` by default, but allow override.
- Generated reports go under `.run/` by default.

---

### Task 1: Smoke Orchestrator Contract

**Agent:** Agent 1 - Smoke Contract Implementer

**Files:**
- Modify: `scripts/smoke/run_real_smoke.py`
- Modify: `tests/smoke/test_real_smoke_orchestrator.py`

- [ ] **Step 1: Write failing tests for new phase order**

Add tests asserting that full local smoke includes source-pack compile and runtime import proof after smoke-full:

```python
def test_local_full_includes_source_pack_and_runtime_import_phases(
    real_smoke: Any,
    fake_subprocess: list[list[str]],
    fake_health: list[str],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "local-full.json"
    monkeypatch.setenv("CONTEXT_BUNDLE_RUNTIME_IMPORT_COMMAND", "python -c import-ok")

    code = run_cli(
        real_smoke,
        ["--target", "local", "--full", "--json-report", str(report_path)],
    )

    assert code == 0
    assert phase_names(report_path) == [
        "readiness",
        "contracts",
        "health",
        "smoke-min",
        "smoke-full",
        "source-pack-compile",
        "runtime-import",
    ]
    executed = [command_text(command).replace("\\", "/") for command in fake_subprocess]
    assert any("scripts/source_pack/compile_context_bundle.py" in command for command in executed)
    assert any("scripts/smoke/runtime_import_probe.py" in command for command in executed)
    assert fake_health == ["http://localhost:8000/health"]
```

- [ ] **Step 2: Run RED**

Run:

```powershell
uv run --cache-dir .uv-cache pytest tests\smoke\test_real_smoke_orchestrator.py::test_local_full_includes_source_pack_and_runtime_import_phases -q
```

Expected: fail because `source-pack-compile` and `runtime-import` phases do not exist.

- [ ] **Step 3: Implement phase args and phase builder**

In `scripts/smoke/run_real_smoke.py`, add args:

```python
parser.add_argument(
    "--source-pack-dir",
    default=r"C:\tmp\context-builder-sources\compounding-pharmacy-gold",
    help="Source pack directory used for context_bundle.v1 compile proof.",
)
parser.add_argument(
    "--skip-source-pack-compile",
    action="store_true",
    help="Skip context_bundle.v1 source-pack compile proof.",
)
parser.add_argument(
    "--skip-runtime-import",
    action="store_true",
    help="Skip external runtime import proof.",
)
```

Append phases after `smoke-full` when `args.full` is true:

```python
if args.full and not args.skip_source_pack_compile:
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
            timeout_seconds=900.0,
            env_overrides=common_env,
        )
    )

if args.full and not args.skip_runtime_import:
    phases.append(
        Phase(
            "runtime-import",
            "subprocess",
            python_cmd("scripts/smoke/runtime_import_probe.py"),
            timeout_seconds=900.0,
            env_overrides=common_env,
        )
    )
```

- [ ] **Step 4: Run GREEN**

Run:

```powershell
uv run --cache-dir .uv-cache pytest tests\smoke\test_real_smoke_orchestrator.py -q
```

Expected: all orchestrator tests pass after existing tests are updated for the new full phase order.

- [ ] **Step 5: Commit**

```powershell
git add scripts/smoke/run_real_smoke.py tests/smoke/test_real_smoke_orchestrator.py
git commit -m "feat: add context bundle proof phases to real smoke"
```

---

### Task 2: Runtime Import Probe

**Agent:** Agent 3 - Runtime Import Adapter Implementer

**Files:**
- Create: `scripts/smoke/runtime_import_probe.py`
- Create: `tests/smoke/test_runtime_import_probe.py`

- [ ] **Step 1: Write failing tests**

Create `tests/smoke/test_runtime_import_probe.py` with:

```python
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "scripts" / "smoke" / "runtime_import_probe.py"


def load_probe() -> Any:
    spec = importlib.util.spec_from_file_location("runtime_import_probe_under_test", PROBE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["runtime_import_probe_under_test"] = module
    spec.loader.exec_module(module)
    return module


def run_cli(module: Any, argv: list[str]) -> int:
    try:
        return int(module.main(argv) or 0)
    except SystemExit as exc:
        return int(exc.code or 0)


def test_missing_runtime_import_command_fails(tmp_path: Path, monkeypatch: Any) -> None:
    probe = load_probe()
    monkeypatch.delenv("CONTEXT_BUNDLE_RUNTIME_IMPORT_COMMAND", raising=False)
    report = tmp_path / "runtime-import.json"

    code = run_cli(probe, ["--json-report", str(report)])

    assert code == 2
    body = json.loads(report.read_text(encoding="utf-8"))
    assert body["status"] == "failed"
    assert body["error"] == "runtime_import_command_required"


def test_runtime_import_command_success_writes_sanitized_report(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    probe = load_probe()
    secret = "test-service-role-secret"
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", secret)
    report = tmp_path / "runtime-import.json"
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout=f"ok {secret}", stderr="")

    monkeypatch.setattr(probe.subprocess, "run", fake_run)

    code = run_cli(
        probe,
        [
            "--bundle-path",
            r"C:\tmp\context-builder-sources\compounding-pharmacy-gold\compounding-pharmacy-gold.context_bundle.v1.json",
            "--command",
            "python -m runtime.importer --bundle {bundle}",
            "--json-report",
            str(report),
        ],
    )

    assert code == 0
    assert calls
    assert calls[0][-1].endswith("compounding-pharmacy-gold.context_bundle.v1.json")
    text = report.read_text(encoding="utf-8")
    assert secret not in text
    assert "[REDACTED]" in text


def test_runtime_import_command_failure_returns_one(tmp_path: Path, monkeypatch: Any) -> None:
    probe = load_probe()
    report = tmp_path / "runtime-import.json"

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 42, stdout="", stderr="runtime rejected bundle")

    monkeypatch.setattr(probe.subprocess, "run", fake_run)

    code = run_cli(
        probe,
        ["--command", "python -m runtime.importer --bundle {bundle}", "--json-report", str(report)],
    )

    assert code == 1
    body = json.loads(report.read_text(encoding="utf-8"))
    assert body["status"] == "failed"
    assert body["returncode"] == 42
```

- [ ] **Step 2: Run RED**

Run:

```powershell
uv run --cache-dir .uv-cache pytest tests\smoke\test_runtime_import_probe.py -q
```

Expected: fail because `scripts/smoke/runtime_import_probe.py` does not exist.

- [ ] **Step 3: Implement minimal probe**

Create `scripts/smoke/runtime_import_probe.py`:

```python
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Mapping, Sequence

from scripts.smoke.run_real_smoke import sanitize_text

DEFAULT_BUNDLE_PATH = (
    r"C:\tmp\context-builder-sources\compounding-pharmacy-gold"
    r"\compounding-pharmacy-gold.context_bundle.v1.json"
)


@dataclass
class RuntimeImportReport:
    status: str
    started_at: str
    finished_at: str | None = None
    command: list[str] | None = None
    bundle_path: str = DEFAULT_BUNDLE_PATH
    returncode: int | None = None
    duration_seconds: float = 0.0
    stdout_tail: str = ""
    stderr_tail: str = ""
    error: str | None = None


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def tail(text: str, limit: int = 4000) -> str:
    return text[-limit:] if len(text) > limit else text


def render_command(template: str, bundle_path: str) -> list[str]:
    rendered = template.replace("{bundle}", bundle_path)
    return shlex.split(rendered, posix=False)


def write_report(path: str, report: RuntimeImportReport, env: Mapping[str, str]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(asdict(report), indent=2, sort_keys=True)
    target.write_text(sanitize_text(payload, env), encoding="utf-8")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run external context_bundle.v1 runtime import proof.")
    parser.add_argument("--bundle-path", default=DEFAULT_BUNDLE_PATH)
    parser.add_argument("--command", default=None)
    parser.add_argument("--json-report", default=None)
    parser.add_argument("--timeout-seconds", type=float, default=900.0)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    env = os.environ.copy()
    command_template = args.command or env.get("CONTEXT_BUNDLE_RUNTIME_IMPORT_COMMAND")
    report = RuntimeImportReport(status="running", started_at=utc_now(), bundle_path=args.bundle_path)

    if not command_template:
        report.status = "failed"
        report.finished_at = utc_now()
        report.error = "runtime_import_command_required"
        if args.json_report:
            write_report(args.json_report, report, env)
        print("ERROR: runtime import command required", file=sys.stderr)
        return 2

    command = render_command(command_template, args.bundle_path)
    report.command = [sanitize_text(part, env) for part in command]
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=args.timeout_seconds,
            check=False,
        )
        report.duration_seconds = round(time.perf_counter() - started, 3)
        report.returncode = completed.returncode
        report.stdout_tail = sanitize_text(tail(completed.stdout or ""), env)
        report.stderr_tail = sanitize_text(tail(completed.stderr or ""), env)
        report.status = "passed" if completed.returncode == 0 else "failed"
    except subprocess.TimeoutExpired as exc:
        report.duration_seconds = round(time.perf_counter() - started, 3)
        report.status = "failed"
        report.error = f"Timed out after {args.timeout_seconds:g}s"
        report.stdout_tail = sanitize_text(tail(exc.stdout or ""), env)
        report.stderr_tail = sanitize_text(tail(exc.stderr or ""), env)

    report.finished_at = utc_now()
    if args.json_report:
        write_report(args.json_report, report, env)
    return 0 if report.status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run GREEN**

Run:

```powershell
uv run --cache-dir .uv-cache pytest tests\smoke\test_runtime_import_probe.py tests\smoke\test_real_smoke_orchestrator.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add scripts/smoke/runtime_import_probe.py tests/smoke/test_runtime_import_probe.py scripts/smoke/run_real_smoke.py tests/smoke/test_real_smoke_orchestrator.py
git commit -m "feat: add runtime import smoke probe"
```

---

### Task 3: Deterministic Bundle Proof

**Agent:** Agent 2 - Source Pack Proof Implementer

**Files:**
- Modify: `scripts/smoke/run_real_smoke.py`
- Modify: `tests/smoke/test_real_smoke_orchestrator.py`

- [ ] **Step 1: Write failing test for repeated compile proof**

Add:

```python
def test_source_pack_compile_phase_can_run_deterministic_check(
    real_smoke: Any,
    tmp_path: Path,
) -> None:
    args = real_smoke.parse_args(
        [
            "--target",
            "local",
            "--full",
            "--source-pack-dir",
            r"C:\tmp\context-builder-sources\compounding-pharmacy-gold",
            "--skip-runtime-import",
            "--dry-run",
        ]
    )
    phases = real_smoke.build_phases(args, {"API_BASE_URL": "http://localhost:8000"})
    compile_phase = next(phase for phase in phases if phase.name == "source-pack-compile")
    command = command_text(compile_phase.command).replace("\\", "/")
    assert "scripts/source_pack/compile_context_bundle.py" in command
    assert "--check" in command
    assert "compounding-pharmacy-gold" in command
```

- [ ] **Step 2: Run RED**

Run:

```powershell
uv run --cache-dir .uv-cache pytest tests\smoke\test_real_smoke_orchestrator.py::test_source_pack_compile_phase_can_run_deterministic_check -q
```

Expected: fail until Task 1 phase is present.

- [ ] **Step 3: Ensure compile phase is deterministic check**

Keep the source-pack phase command exactly:

```python
python_cmd(
    "scripts/source_pack/compile_context_bundle.py",
    "--source-dir",
    args.source_pack_dir,
    "--check",
)
```

Do not add a second compiler. Do not compute hash in the smoke orchestrator; the compiler owns canonicalization and hash validation.

- [ ] **Step 4: Run GREEN**

Run:

```powershell
uv run --cache-dir .uv-cache pytest tests\smoke\test_real_smoke_orchestrator.py tests\compat\test_compounding_pharmacy_source_pack_compiler.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add scripts/smoke/run_real_smoke.py tests/smoke/test_real_smoke_orchestrator.py
git commit -m "test: prove source pack compile in real smoke"
```

---

### Task 4: Smoke Documentation And Task Closure

**Agent:** Agent 4 - Documentation/Runbook Implementer

**Files:**
- Modify: `tasks/TASK-022-real-smoke-runtime-import.md`
- Modify: `docs/operations/smoke-runbook.md`

- [ ] **Step 1: Update migration references**

In `docs/operations/smoke-runbook.md`, change migration scope from `000` to `045` to `000` to `047`, and explicitly mention:

```text
046_source_pack_import_runs.sql
047_context_build_runs.sql
```

- [ ] **Step 2: Add runtime import proof instructions**

Add this command block to the full smoke section:

```powershell
$env:CONTEXT_BUNDLE_RUNTIME_IMPORT_COMMAND="python -m runtime.importer --bundle {bundle}"
uv run --cache-dir .uv-cache python scripts\smoke\run_real_smoke.py --target local --full --json-report .run\smoke-local-full.json
```

Add note:

```text
Replace the command with the selected consumer runtime import command. The
placeholder `{bundle}` is replaced by the generated context_bundle.v1 path.
Do not put secrets in the command.
```

- [ ] **Step 3: Update TASK-022 status language**

Set status to:

```text
Status: implementation planned; pending real environment execution.
```

Add a checklist:

```markdown
## Execution Checklist

- [ ] Docker/Supabase runtime is already running.
- [ ] Migrations through `047` are applied.
- [ ] `scripts/smoke/run_real_smoke.py --target local --full` passes.
- [ ] Source pack compile phase writes deterministic bundle hash.
- [ ] Runtime import phase passes with selected consumer runtime command.
- [ ] JSON reports are stored under `.run/` and contain no secrets.
```

- [ ] **Step 4: Run docs/task grep**

Run:

```powershell
rg -n "000.*045|migrations `000` a `045`|047|runtime import|CONTEXT_BUNDLE_RUNTIME_IMPORT_COMMAND" docs/operations/smoke-runbook.md tasks/TASK-022-real-smoke-runtime-import.md
```

Expected: no stale `000` to `045` scope remains except historical troubleshooting if explicitly labelled.

- [ ] **Step 5: Commit**

```powershell
git add docs/operations/smoke-runbook.md tasks/TASK-022-real-smoke-runtime-import.md
git commit -m "docs: plan real smoke runtime import proof"
```

---

### Task 5: Final Review And Real Run Gate

**Agent:** Controller plus Agent 5 and Agent 6 reviewers

**Files:**
- Review-only unless blockers require fixes.

- [ ] **Step 1: Run local gates**

Run:

```powershell
uv run --cache-dir .uv-cache pytest tests\smoke\test_real_smoke_orchestrator.py tests\smoke\test_runtime_import_probe.py -q
uv run --cache-dir .uv-cache pytest -q
uv run --cache-dir .uv-cache ruff check .
npm run typecheck:python:strict-full
uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py
```

Expected:

```text
all tests pass
ruff passes
mypy passes
secret scan passes
```

- [ ] **Step 2: Spec review**

Dispatch Agent 5 with one function:

```text
Review TASK-022 implementation against acceptance only. Do not edit files.
Verify: real smoke phases, migrations through 047, context_build_runs and
source_pack_import_runs coverage, source-pack compile proof, deterministic hash
proof, runtime import proof, cited-answer/blocker verification documented, and
secret-free report requirements. Return APROVADO or BLOQUEADORES.
```

- [ ] **Step 3: Quality/security review**

Dispatch Agent 6 with one function:

```text
Review TASK-022 implementation for quality/security only. Do not edit files.
Focus: subprocess safety, shell parsing, secret redaction, report path handling,
timeouts, skip flags, path leakage, destructive commands, and Windows behavior.
Return APROVADO or BLOQUEADORES.
```

- [ ] **Step 4: Fix review blockers with TDD**

For each blocker:

1. Add a failing test that reproduces it.
2. Run the test and confirm RED.
3. Implement the minimal fix.
4. Run focused test and full relevant gate.
5. Ask the same reviewer to re-review.

- [ ] **Step 5: Real environment execution**

Only after local gates and reviews pass, run:

```powershell
uv run --cache-dir .uv-cache python scripts\smoke\run_real_smoke.py --target local --full --json-report .run\smoke-local-full.json
```

Expected:

```text
[PASSED] readiness
[PASSED] contracts
[PASSED] health
[PASSED] smoke-min
[PASSED] smoke-full
[PASSED] source-pack-compile
[PASSED] runtime-import
```

If runtime command is not yet selected, run once with:

```powershell
uv run --cache-dir .uv-cache python scripts\smoke\run_real_smoke.py --target local --full --skip-runtime-import --json-report .run\smoke-local-full-no-runtime.json
```

Then keep `TASK-022` open as pending runtime import proof.

---

## TASK-012 Follow-Up Plan Boundary

Do not start repository clean-slate cleanup until TASK-022 has either:

- passed full runtime import proof, or
- produced a dated smoke report showing the only remaining blocker is outside this repository.

TASK-012 needs a separate plan because it may touch the original dirty checkout and can require destructive cleanup. It must start with read-only inventory:

```powershell
git status --short --branch
git diff --stat
git stash list
git worktree list
```

No delete, reset, restore, or move is allowed without explicit approval.

---

## Final Verification Commands

```powershell
uv run --cache-dir .uv-cache pytest tests\smoke\test_real_smoke_orchestrator.py tests\smoke\test_runtime_import_probe.py -q
uv run --cache-dir .uv-cache pytest -q
uv run --cache-dir .uv-cache ruff check .
npm run typecheck:python:strict-full
uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py
uv run --cache-dir .uv-cache python scripts\smoke\run_real_smoke.py --target local --full --json-report .run\smoke-local-full.json
```

## Self-Review

- Spec coverage: TASK-022 acceptance is covered by Tasks 1-5.
- Placeholder scan: no `TBD`, `TODO`, or unspecified implementation slots remain. The runtime command is intentionally configurable because the consumer runtime is external.
- Type consistency: phase names are stable: `source-pack-compile` and `runtime-import`; env var is stable: `CONTEXT_BUNDLE_RUNTIME_IMPORT_COMMAND`; default bundle path matches the compounding pharmacy source pack output.
