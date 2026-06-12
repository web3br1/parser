# Production Smoke Readiness SDD Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining production-level smoke, UX, audit, runtime import, semantic, CI, and documentation gaps before declaring the Parser ready for production pilot data.

**Architecture:** Keep the current FastAPI, Supabase, Celery, source-pack compiler, Next.js console, and smoke-orchestrator architecture. Add narrow production-readiness gates around the existing smoke scripts instead of replacing them, and make the Wizard consume the persisted `context_build_runs` contract instead of local-only state. Each agent owns a non-overlapping slice and must leave a fresh verification trail.

**Tech Stack:** Python 3.12, pytest, ruff, uv, FastAPI, Supabase/Postgres, Playwright, Node.js, Next.js App Router, React, TypeScript, Tailwind, existing `scripts/smoke/*`, existing `scripts/pilot/*`, existing `apps/web/src/lib/api.ts`.

---

## SDD Agent Split

Run tasks sequentially. Do not dispatch implementation agents in parallel because several tasks share smoke scripts, docs, and API types.

1. **Agent A - Runtime Import Gate:** production readiness contract for runtime import, no `--skip-runtime-import` in production mode.
2. **Agent B - Audit E2E Smoke:** verify audit rows for context bundle export and workflow lifecycle.
3. **Agent C - Wizard Runs UX/API:** add the `Runs` tab and API polish around `context_build_runs`.
4. **Agent D - Browser Smoke:** promote Wizard + Tutor smoke into a stable production browser gate.
5. **Agent E - Semantic Gate:** wire semantic metrics into release readiness.
6. **Agent F - CI/Docs/Hygiene:** update CI/runbooks and exclude local brainstorming artifacts.

Each task requires:

- implementer subagent;
- spec-compliance reviewer subagent;
- code-quality reviewer subagent;
- focused tests before moving to the next task.

---

## Task 1: Runtime Import Production Gate

**Files:**
- Modify: `scripts/smoke/run_real_smoke.py`
- Modify: `scripts/smoke/runtime_import_probe.py`
- Modify: `tests/smoke/test_real_smoke_orchestrator.py`
- Modify: `tests/smoke/test_runtime_import_probe.py`
- Modify: `docs/operations/smoke-runbook.md`
- Modify: `docs/00-start-here/USER_GUIDE.md`

- [ ] **Step 1: Add failing orchestrator tests for production mode**

Add tests to `tests/smoke/test_real_smoke_orchestrator.py`:

```python
def test_production_profile_requires_full_mode(real_smoke: Any) -> None:
    assert run_cli(real_smoke, ["--profile", "production"]) == 2


def test_production_profile_rejects_skip_runtime_import(real_smoke: Any) -> None:
    assert (
        run_cli(
            real_smoke,
            ["--target", "local", "--full", "--profile", "production", "--skip-runtime-import"],
        )
        == 2
    )


def test_production_profile_includes_runtime_import(real_smoke: Any) -> None:
    args = real_smoke.parse_args(["--target", "local", "--full", "--profile", "production"])
    phases = real_smoke.build_phases(args, {"CONTEXT_BUNDLE_RUNTIME_IMPORT_COMMAND": "python -c pass {bundle}"})
    assert [phase.name for phase in phases][-1] == "runtime-import"
```

- [ ] **Step 2: Run focused failing tests**

Run:

```powershell
uv run --cache-dir .uv-cache pytest tests\smoke\test_real_smoke_orchestrator.py -q
```

Expected before implementation: tests that reference `--profile` fail because the argument does not exist.

- [ ] **Step 3: Implement production profile validation**

In `scripts/smoke/run_real_smoke.py`, add:

```python
parser.add_argument("--profile", choices=("dev", "production"), default="dev")
```

Extend `validate_args`:

```python
if args.profile == "production" and not args.full:
    return "--profile production requires --full"
if args.profile == "production" and args.skip_runtime_import:
    return "--profile production cannot use --skip-runtime-import"
if args.profile == "production" and not env.get("CONTEXT_BUNDLE_RUNTIME_IMPORT_COMMAND"):
    return "--profile production requires CONTEXT_BUNDLE_RUNTIME_IMPORT_COMMAND"
```

- [ ] **Step 4: Add runtime import report guard tests**

In `tests/smoke/test_runtime_import_probe.py`, add a test that proves `{bundle}` is mandatory in the command template:

```python
def test_runtime_import_command_requires_bundle_placeholder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    report_path = tmp_path / "runtime-import.json"
    code = run_probe(
        [
            "--command",
            f'"{sys.executable}" -c pass',
            "--json-report",
            str(report_path),
        ],
        monkeypatch,
    )
    assert code == 2
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["error"] == "runtime_import_command_missing_bundle_placeholder"
```

- [ ] **Step 5: Implement placeholder validation**

In `scripts/smoke/runtime_import_probe.py`, reject command templates that do not contain `{bundle}`:

```python
if "{bundle}" not in command_template:
    report = failed_config_report(
        args,
        started_at,
        started,
        "runtime_import_command_missing_bundle_placeholder",
    )
    print("ERROR: runtime import command must include {bundle}", file=sys.stderr)
    if args.json_report:
        write_report(args.json_report, report, env)
    return 2
```

- [ ] **Step 6: Update production commands in docs**

Document the production command:

```powershell
$env:CONTEXT_BUNDLE_RUNTIME_IMPORT_COMMAND="<consumer-runtime-command> --bundle ""{bundle}"""
uv run --cache-dir .uv-cache python scripts\smoke\run_real_smoke.py --target local --full --profile production --json-report .run\smoke-local-production.json
```

Use the wording: "The command must be supplied by the consumer runtime project; the Parser repository only verifies that the generated `context_bundle.v1` is accepted without manual editing."

- [ ] **Step 7: Verify Task 1**

Run:

```powershell
uv run --cache-dir .uv-cache pytest tests\smoke\test_real_smoke_orchestrator.py tests\smoke\test_runtime_import_probe.py -q
uv run --cache-dir .uv-cache ruff check scripts\smoke\run_real_smoke.py scripts\smoke\runtime_import_probe.py tests\smoke\test_real_smoke_orchestrator.py tests\smoke\test_runtime_import_probe.py
```

Expected: all pass.

**Definition of done:** A production smoke command cannot silently skip runtime import and cannot run without an explicit consumer import command containing `{bundle}`.

---

## Task 2: Audit E2E Smoke

**Files:**
- Create: `scripts/smoke/audit_e2e_probe.py`
- Create: `tests/smoke/test_audit_e2e_probe.py`
- Modify: `scripts/smoke/run_real_smoke.py`
- Modify: `tests/smoke/test_real_smoke_orchestrator.py`
- Modify: `docs/operations/smoke-runbook.md`

- [ ] **Step 1: Add probe tests with fake REST client**

Create `tests/smoke/test_audit_e2e_probe.py` with:

```python
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "scripts" / "smoke" / "audit_e2e_probe.py"


def load_probe() -> Any:
    spec = importlib.util.spec_from_file_location("audit_e2e_probe_under_test", PROBE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["audit_e2e_probe_under_test"] = module
    spec.loader.exec_module(module)
    return module


def test_audit_probe_passes_when_required_actions_exist(tmp_path: Path, monkeypatch: Any) -> None:
    module = load_probe()
    monkeypatch.setattr(
        module,
        "fetch_audit_actions",
        lambda workspace_id, env: {"context_bundle.export", "query.answer"},
    )
    report = tmp_path / "audit.json"
    code = module.main(["--workspace-id", "ws_1", "--json-report", str(report)])
    assert code == 0
    body = json.loads(report.read_text(encoding="utf-8"))
    assert body["status"] == "passed"


def test_audit_probe_fails_when_context_bundle_export_missing(tmp_path: Path, monkeypatch: Any) -> None:
    module = load_probe()
    monkeypatch.setattr(module, "fetch_audit_actions", lambda workspace_id, env: {"query.answer"})
    report = tmp_path / "audit.json"
    code = module.main(["--workspace-id", "ws_1", "--json-report", str(report)])
    assert code == 1
    body = json.loads(report.read_text(encoding="utf-8"))
    assert body["missing_actions"] == ["context_bundle.export"]
```

- [ ] **Step 2: Run failing probe tests**

Run:

```powershell
uv run --cache-dir .uv-cache pytest tests\smoke\test_audit_e2e_probe.py -q
```

Expected before implementation: import fails because `scripts/smoke/audit_e2e_probe.py` does not exist.

- [ ] **Step 3: Implement audit probe**

Create `scripts/smoke/audit_e2e_probe.py`:

```python
from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

SMOKE_DIR = Path(__file__).resolve().parent
if str(SMOKE_DIR) not in sys.path:
    sys.path.insert(0, str(SMOKE_DIR))

from run_real_smoke import sanitize_text  # noqa: E402

REQUIRED_ACTIONS = ("context_bundle.export",)


@dataclass
class AuditProbeReport:
    status: str
    workspace_id: str
    required_actions: list[str]
    observed_actions: list[str]
    missing_actions: list[str]


def fetch_audit_actions(workspace_id: str, env: Mapping[str, str]) -> set[str]:
    from scripts.smoke.supabase_smoke import supabase_rest

    rows = supabase_rest(
        "audit_logs",
        params={
            "workspace_id": f"eq.{workspace_id}",
            "select": "action",
            "order": "created_at.desc",
            "limit": "100",
        },
    )
    return {str(row.get("action")) for row in rows if row.get("action")}


def write_report(path: str, report: AuditProbeReport, env: Mapping[str, str]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(sanitize_text(json.dumps(asdict(report), indent=2, sort_keys=True), env), encoding="utf-8")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify production-critical audit logs exist after smoke.")
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--json-report")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    env = os.environ.copy()
    observed = sorted(fetch_audit_actions(args.workspace_id, env))
    missing = [action for action in REQUIRED_ACTIONS if action not in observed]
    report = AuditProbeReport(
        status="failed" if missing else "passed",
        workspace_id=args.workspace_id,
        required_actions=list(REQUIRED_ACTIONS),
        observed_actions=observed,
        missing_actions=missing,
    )
    if args.json_report:
        write_report(args.json_report, report, env)
    if missing:
        print(f"Missing audit actions: {', '.join(missing)}")
        return 1
    print("Audit probe passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Feed smoke workspace IDs into orchestration report**

Modify `scripts/smoke/run_real_smoke.py` to parse child smoke JSON reports after `smoke-min` and `smoke-full`, copying `workspace_id` from the sub-report into each `PhaseResult` metadata. Add a `metadata: dict[str, str] = field(default_factory=dict)` field to `PhaseResult`.

- [ ] **Step 5: Add audit phase after smoke-full**

In `build_phases`, add `audit-e2e` after `smoke-full` when `args.full` and `not args.skip_audit_probe`. Pass the full-smoke workspace id through an environment variable `SMOKE_AUDIT_WORKSPACE_ID` after the `smoke-full` phase has completed. The task is sequential; do not run audit probe before the full-smoke report exists.

- [ ] **Step 6: Add orchestrator tests**

In `tests/smoke/test_real_smoke_orchestrator.py`, assert full production phase order:

```python
assert phase_names(report_path) == [
    "readiness",
    "contracts",
    "health",
    "smoke-min",
    "smoke-full",
    "audit-e2e",
    "source-pack-compile",
    "runtime-import",
]
```

- [ ] **Step 7: Verify Task 2**

Run:

```powershell
uv run --cache-dir .uv-cache pytest tests\smoke\test_audit_e2e_probe.py tests\smoke\test_real_smoke_orchestrator.py -q
uv run --cache-dir .uv-cache ruff check scripts\smoke\audit_e2e_probe.py scripts\smoke\run_real_smoke.py tests\smoke
```

Expected: all pass.

**Definition of done:** Full smoke can fail production readiness when `context_bundle.export` audit evidence is missing.

---

## Task 3: Wizard Runs UX/API Polish

**Files:**
- Modify: `apps/web/src/lib/api.ts`
- Modify: `apps/web/src/components/context-build-wizard.tsx`
- Create: `apps/web/src/components/context-build-runs-panel.tsx`
- Create: `apps/web/src/components/copy-field.tsx`
- Test: `scripts/smoke/context_build_wizard_tutor_smoke.mjs`
- Optional API test if backend shape changes: `tests/api/test_context_build_runs.py`

- [ ] **Step 1: Add frontend run summary helper**

Create `apps/web/src/lib/context-build-runs.ts`:

```ts
export type ContextBuildRunSummaryInput = {
  id: string;
  status: string;
  input_mode: string;
  recommended_action: string;
  bundle_hash: string | null;
  context_version: string | null;
  output_path: string | null;
  readiness_status: string | null;
  warnings: string[];
  errors: string[];
  created_at: string;
  updated_at: string;
};

export function summarizeContextBuildRun(run: ContextBuildRunSummaryInput) {
  return {
    id: run.id,
    primaryStatus: run.readiness_status ?? run.status,
    bundleAvailable: Boolean(run.bundle_hash || run.output_path),
    hasProblems: run.errors.length > 0 || run.readiness_status === "blocked",
  };
}
```

- [ ] **Step 2: Add API client functions**

In `apps/web/src/lib/api.ts`, export:

```ts
export type ContextBuildRunResponse = ContextBuildRunApiResponse & {
  workspace_id: string;
  actor_user_id: string | null;
  input_mode: "single_document" | "multi_document_batch" | "source_pack";
  recommended_action: "compile_as_source_pack" | "normal_ingest" | "batch_ingest" | "reject" | string;
  input_fingerprint: string;
  input_hash: string | null;
  source_pack_id: string | null;
  source_pack_version: string | null;
  staged_upload_id: string | null;
  source_count: number;
  job_count: number;
  output_path: string | null;
  readiness_score: number | null;
  file_counts: Record<string, number>;
  missing_files: string[];
  extra_files: string[];
  steps: Array<Record<string, unknown>>;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export async function listContextBuildRuns(
  workspaceId: string,
  token: string
): Promise<ContextBuildRunResponse[]> {
  return apiFetch<ContextBuildRunResponse[]>(`/workspaces/${workspaceId}/context-build-runs`, {
    method: "GET",
    token
  });
}
```

- [ ] **Step 3: Split Wizard into tabs**

Modify `apps/web/src/components/context-build-wizard.tsx`:

- Add local state: `const [activeTab, setActiveTab] = useState<"new" | "runs">("new");`
- Render two tab buttons: `Novo build` and `Runs`.
- Keep the existing wizard content under `activeTab === "new"`.
- Render `<ContextBuildRunsPanel workspaceId={workspaceId} token={token} latestRunId={compileResult?.run_id ?? preflight?.run_id ?? null} />` under `activeTab === "runs"`.

- [ ] **Step 4: Implement master-detail Runs panel**

Create `apps/web/src/components/context-build-runs-panel.tsx` with:

- fetch on mount and on refresh click;
- left list of recent runs ordered by `created_at`;
- right detail for selected run;
- visible fields: status, readiness, source pack id/version, counts, warnings, blockers, context version, bundle hash, output path;
- buttons for copying bundle hash, context version, and output path;
- empty, loading, error, and retry states.

- [ ] **Step 5: Implement clipboard component**

Create `apps/web/src/components/copy-field.tsx` with:

- `navigator.clipboard.writeText(value)`;
- fallback to selecting a readonly input when clipboard API is unavailable;
- `aria-label` for each copy button;
- copied state text that returns to idle after 1500 ms.

- [ ] **Step 6: Extend browser smoke assertions**

In `scripts/smoke/context_build_wizard_tutor_smoke.mjs`, after final compile:

```js
await page.getByRole("button", { name: "Runs" }).click();
await page.getByText("bundle_hash", { exact: false }).waitFor({ state: "visible", timeout: 30_000 });
await page.getByRole("button", { name: /Copy bundle hash/i }).waitFor({ state: "visible", timeout: 30_000 });
result.checks.runs_tab_bundle_details = true;
```

- [ ] **Step 7: Verify Task 3**

Run:

```powershell
npm run typecheck
node scripts\smoke\context_build_wizard_tutor_smoke.mjs --base-url http://127.0.0.1:3000 --api-url http://localhost:8000
```

Expected: typecheck and the Wizard + Tutor smoke pass.

**Definition of done:** Operators can open a `Runs` tab, inspect persisted context builds, and copy bundle output identifiers without relying on transient local Wizard state.

---

## Task 4: Production Browser Smoke Gate

**Files:**
- Modify: `scripts/smoke/frontend_console_smoke.mjs`
- Modify: `scripts/smoke/context_build_wizard_tutor_smoke.mjs`
- Create: `scripts/smoke/run_browser_smoke_suite.mjs`
- Create: `tests/smoke/test_browser_smoke_scripts.py`
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Add smoke script inventory test**

Create `tests/smoke/test_browser_smoke_scripts.py`:

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_browser_smoke_suite_script_exists() -> None:
    script = ROOT / "scripts" / "smoke" / "run_browser_smoke_suite.mjs"
    assert script.exists()
    text = script.read_text(encoding="utf-8")
    assert "frontend_console_smoke.mjs" in text
    assert "context_build_wizard_tutor_smoke.mjs" in text
```

- [ ] **Step 2: Run failing inventory test**

Run:

```powershell
uv run --cache-dir .uv-cache pytest tests\smoke\test_browser_smoke_scripts.py -q
```

Expected before implementation: fails because `run_browser_smoke_suite.mjs` does not exist.

- [ ] **Step 3: Create browser smoke suite wrapper**

Create `scripts/smoke/run_browser_smoke_suite.mjs`:

```js
#!/usr/bin/env node

import { spawnSync } from "node:child_process";

const baseUrl = process.env.FRONTEND_SMOKE_BASE_URL ?? "http://127.0.0.1:3000";
const apiUrl = process.env.API_BASE_URL ?? "http://localhost:8000";

const commands = [
  ["node", ["scripts/smoke/frontend_console_smoke.mjs", "--base-url", baseUrl, "--route", "/workspaces/demo/context-build", "--route-timeout-ms", "15000"]],
  ["node", ["scripts/smoke/context_build_wizard_tutor_smoke.mjs", "--base-url", baseUrl, "--api-url", apiUrl]],
];

let failed = false;
for (const [command, args] of commands) {
  const result = spawnSync(command, args, { stdio: "inherit", shell: false });
  if (result.status !== 0) {
    failed = true;
    break;
  }
}

process.exitCode = failed ? 1 : 0;
```

- [ ] **Step 4: Make suite CI-aware**

In `.github/workflows/ci.yml`, keep `frontend_console_smoke.mjs` in CI because it can start a built frontend without real Supabase. Do not run `context_build_wizard_tutor_smoke.mjs` in GitHub CI unless Supabase secrets and a full local runtime are configured. Add a commented/documented manual command in workflow comments or docs, not a disabled CI step.

- [ ] **Step 5: Verify Task 4**

Run:

```powershell
uv run --cache-dir .uv-cache pytest tests\smoke\test_browser_smoke_scripts.py -q
npm run typecheck
node scripts\smoke\frontend_console_smoke.mjs --base-url http://127.0.0.1:3000 --route /workspaces/demo/context-build --route-timeout-ms 15000
```

Expected: tests and lightweight browser smoke pass. The full Wizard + Tutor smoke is run locally with real runtime as part of final readiness.

**Definition of done:** Browser smoke commands are discoverable, repeatable, and split cleanly between CI-safe and real-runtime-required gates.

---

## Task 5: Semantic Production Gate

**Files:**
- Modify: `scripts/pilot/semantic_metrics.py`
- Modify: `scripts/pilot/pilot_metrics.py`
- Modify: `scripts/pilot/run_semireal_pilot.py`
- Modify: `tests/smoke/test_semantic_metrics.py`
- Modify: `tests/smoke/test_pilot_metrics.py`
- Modify: `docs/07-qa/ACCEPTANCE_CRITERIA.md`
- Modify: `docs/07-qa/REGRESSION_GATES.md`

- [ ] **Step 1: Add CLI threshold tests**

In `tests/smoke/test_semantic_metrics.py`, add:

```python
def test_semantic_metrics_cli_fails_when_thresholds_are_not_met(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    predictions = tmp_path / "predictions.json"
    manifest.write_text(
        json.dumps({"documents": [{"filename": "a.txt", "expected": [{"kind": "fact", "type": "service_price", "canonical": "corte|50|BRL"}]}]}),
        encoding="utf-8",
    )
    predictions.write_text(json.dumps([]), encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "pilot" / "semantic_metrics.py"),
            "--manifest",
            str(manifest),
            "--predictions",
            str(predictions),
            "--min-precision",
            "0.85",
            "--min-recall",
            "0.75",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 1
```

- [ ] **Step 2: Implement threshold CLI options**

In `scripts/pilot/semantic_metrics.py`, add:

```python
parser.add_argument("--min-precision", type=float, default=None)
parser.add_argument("--min-recall", type=float, default=None)
parser.add_argument("--max-critical-false-positives", type=int, default=0)
```

Exit with `1` when a supplied threshold fails. Keep `not_evaluated` as exit `2` so operators can distinguish missing predictions from poor quality.

- [ ] **Step 3: Make pilot metrics fail non-zero**

In `scripts/pilot/pilot_metrics.py`, after writing/printing the report:

```python
if report.get("passed") is False:
    raise SystemExit(1)
```

Add a test to `tests/smoke/test_pilot_metrics.py` that builds a failing report and asserts CLI exit `1`.

- [ ] **Step 4: Wire semantic report into semireal pilot**

In `scripts/pilot/run_semireal_pilot.py`, ensure generated semantic metrics are written to `.run/` and surfaced in the final summary with `semantic_passed`.

- [ ] **Step 5: Verify Task 5**

Run:

```powershell
uv run --cache-dir .uv-cache pytest tests\smoke\test_semantic_metrics.py tests\smoke\test_pilot_metrics.py -q
uv run --cache-dir .uv-cache ruff check scripts\pilot tests\smoke\test_semantic_metrics.py tests\smoke\test_pilot_metrics.py
```

Expected: semantic and pilot metric tests pass.

**Definition of done:** Production readiness can fail on semantic quality, not only on mechanical smoke success.

---

## Task 6: Production Readiness Command and Docs

**Files:**
- Create: `scripts/smoke/production_readiness.py`
- Create: `tests/smoke/test_production_readiness.py`
- Modify: `.github/workflows/ci.yml`
- Modify: `.gitignore`
- Modify: `docs/00-start-here/USER_GUIDE.md`
- Modify: `docs/operations/smoke-runbook.md`
- Modify: `docs/07-qa/ACCEPTANCE_CRITERIA.md`
- Modify: `docs/07-qa/REGRESSION_GATES.md`

- [ ] **Step 1: Ignore local brainstorming artifacts**

Add to `.gitignore`:

```gitignore
.superpowers/
```

- [ ] **Step 2: Add production readiness dry-run tests**

Create `tests/smoke/test_production_readiness.py`:

```python
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def test_production_readiness_dry_run_lists_required_gates() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/smoke/production_readiness.py", "--dry-run"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0
    stdout = completed.stdout
    assert "pytest" in stdout
    assert "ruff" in stdout
    assert "run_real_smoke.py --target local --full --profile production" in stdout
    assert "context_build_wizard_tutor_smoke.mjs" in stdout
```

- [ ] **Step 3: Implement production readiness wrapper**

Create `scripts/smoke/production_readiness.py` with a dry-run by default and explicit `--run-local-static` for static checks:

```python
from __future__ import annotations

import argparse
import subprocess
from collections.abc import Sequence

COMMANDS = [
    ["uv", "run", "--cache-dir", ".uv-cache", "pytest", "-q"],
    ["uv", "run", "--cache-dir", ".uv-cache", "ruff", "check", "."],
    ["npm", "run", "typecheck:python"],
    ["npm", "run", "typecheck:python:strict-full"],
    ["npm", "run", "typecheck"],
    ["corepack", "pnpm", "--filter", "@context-builder/web", "build"],
    ["uv", "run", "--cache-dir", ".uv-cache", "python", "scripts/ci/secret_scan.py"],
]

REAL_RUNTIME_COMMANDS = [
    ["uv", "run", "--cache-dir", ".uv-cache", "python", "scripts/smoke/run_real_smoke.py", "--target", "local", "--full", "--profile", "production", "--json-report", ".run/smoke-local-production.json"],
    ["node", "scripts/smoke/context_build_wizard_tutor_smoke.mjs", "--base-url", "http://127.0.0.1:3000", "--api-url", "http://localhost:8000"],
]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run or print production readiness gates.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--run-local-static", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    all_commands = COMMANDS + REAL_RUNTIME_COMMANDS
    if args.dry_run or not args.run_local_static:
        for command in all_commands:
            print(" ".join(command))
        return 0
    for command in COMMANDS:
        completed = subprocess.run(command, check=False)
        if completed.returncode != 0:
            return completed.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Update CI**

In `.github/workflows/ci.yml`, add:

```yaml
      - run: uv run python scripts/smoke/production_readiness.py --dry-run
```

Do not run real-runtime commands in GitHub CI unless the runtime and secrets are explicitly configured.

- [ ] **Step 5: Update docs**

Update docs with three readiness levels:

1. **CI static readiness:** `uv run python scripts/smoke/production_readiness.py --run-local-static`
2. **Local real runtime readiness:** full Docker/API/workers/Supabase plus Wizard smoke.
3. **Production import readiness:** `run_real_smoke.py --profile production` with `CONTEXT_BUNDLE_RUNTIME_IMPORT_COMMAND`.

- [ ] **Step 6: Verify Task 6**

Run:

```powershell
uv run --cache-dir .uv-cache pytest tests\smoke\test_production_readiness.py -q
uv run --cache-dir .uv-cache python scripts\smoke\production_readiness.py --dry-run
uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py
```

Expected: all pass and `.superpowers/` no longer appears as an untracked production artifact.

**Definition of done:** Operators and CI have one production-readiness entrypoint, and local brainstorming artifacts are not accidentally committed.

---

## Final SDD Verification

After all tasks pass their focused gates, run:

```powershell
git status --short --branch
uv run --cache-dir .uv-cache pytest -q
uv run --cache-dir .uv-cache ruff check .
npm run typecheck:python
npm run typecheck:python:strict-full
npm run typecheck
corepack pnpm --filter @context-builder/web build
uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py
uv run --cache-dir .uv-cache python scripts\smoke\production_readiness.py --dry-run
```

With local real runtime already running:

```powershell
node scripts\smoke\context_build_wizard_tutor_smoke.mjs --base-url http://127.0.0.1:3000 --api-url http://localhost:8000
$env:CONTEXT_BUNDLE_RUNTIME_IMPORT_COMMAND="<consumer-runtime-command> --bundle ""{bundle}"""
uv run --cache-dir .uv-cache python scripts\smoke\run_real_smoke.py --target local --full --profile production --json-report .run\smoke-local-production.json
```

Production readiness is not complete until the final command passes without `--skip-runtime-import`.

---

## Self-Review

- Spec coverage: covers runtime import, audit E2E, Wizard Runs UX/API, browser smoke, semantic gate, CI/docs/hygiene.
- Scope: six independent SDD tasks, each with focused ownership and verification.
- External dependency: the actual consumer runtime import command must come from the runtime project. This plan makes the absence explicit and failing in production mode.
- Type consistency: phase names remain stable: `readiness`, `contracts`, `health`, `smoke-min`, `smoke-full`, `audit-e2e`, `source-pack-compile`, `runtime-import`.
