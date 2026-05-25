# Source Pack Import Run Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist every source-pack preflight and compile attempt as an auditable `source_pack_import_runs` record tied to workspace, actor, pack version, readiness, bundle hash and errors.

**Architecture:** Add a Supabase table for import runs, a small FastAPI service that writes/updates runs, and API integration so preflight can optionally create a persisted run. Keep compilation itself in the existing source-pack compiler; this slice only records lifecycle state and evidence needed by later compile/upload/UI slices.

**Tech Stack:** PostgreSQL/Supabase migrations, FastAPI, Pydantic v2, pytest, existing dependency overrides and fake DB test style, `source_pack` package preflight/compiler contracts.

---

## Current Context

Already implemented:

- `packages/source_pack` compiles `C:\tmp\context-builder-sources\compounding-pharmacy-gold` to `context_bundle.v1`.
- `POST /workspaces/{workspace_id}/sources/source-pack/preflight` returns `compile_as_source_pack`, `normal_ingest`, or `reject`.
- Current latest migration is `045_backfill_source_state.sql`; the next migration must be `046_source_pack_import_runs.sql`.

This plan builds the persistence layer required before product upload UX and compile API.

## File Map

Create:

- `supabase/migrations/046_source_pack_import_runs.sql`
- `apps/api/src/context_builder/schemas/source_pack_import.py`
- `apps/api/src/context_builder/services/source_pack_import_runs.py`
- `tests/integrity/test_source_pack_import_runs_migration.py`
- `tests/api/test_source_pack_import_runs.py`
- `tasks/TASK-019-source-pack-import-run-persistence.md`

Modify:

- `apps/api/src/context_builder/routers/sources.py`
- `docs/operations/source-pack-compiler-runbook.md`
- `docs/07-qa/ACCEPTANCE_CRITERIA.md`
- `docs/04-data/DATA_MODEL.md`

Do not modify the compiler behavior except if a failing test proves the persistence service needs one extra field from the existing preflight response.

## Data Contract

Table name:

```sql
public.source_pack_import_runs
```

Lifecycle statuses:

```text
preflighted
compiled
rejected
failed
```

Recommended action values copied from preflight:

```text
compile_as_source_pack
normal_ingest
reject
```

Minimum persisted fields:

```text
id uuid primary key
workspace_id uuid not null
actor_user_id uuid null
source_pack_id text null
source_pack_version text null
source_dir text null
input_hash text not null
status text not null
recommended_action text not null
bundle_hash text null
context_version text null
output_path text null
readiness_status text null
readiness_score integer null
numbered_source_count integer not null default 0
csv_count integer not null default 0
markdown_count integer not null default 0
manifest_document_count integer not null default 0
official_reference_count integer not null default 0
missing_files jsonb not null default '[]'
extra_files jsonb not null default '[]'
warnings jsonb not null default '[]'
errors jsonb not null default '[]'
metadata jsonb not null default '{}'
created_at timestamptz not null default now()
updated_at timestamptz not null default now()
```

The table must use RLS and workspace membership policies consistent with existing workspace-owned tables.

## Task 1: Migration And RLS

**Agent:** Database Contract Agent

**Files:**

- Create: `supabase/migrations/046_source_pack_import_runs.sql`
- Modify: `docs/04-data/DATA_MODEL.md`

- [ ] **Step 1: Write failing integrity tests for the migration**

Create `tests/integrity/test_source_pack_import_runs_migration.py`:

```python
from __future__ import annotations

from pathlib import Path


MIGRATION = Path("supabase/migrations/046_source_pack_import_runs.sql")


def test_source_pack_import_runs_migration_exists() -> None:
    assert MIGRATION.exists()


def test_source_pack_import_runs_table_contract() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "create table public.source_pack_import_runs" in sql
    assert "workspace_id uuid not null references public.workspaces(id)" in sql
    assert "actor_user_id uuid references auth.users(id)" in sql
    assert "source_pack_id text" in sql
    assert "source_pack_version text" in sql
    assert "input_hash text not null" in sql
    assert "bundle_hash text" in sql
    assert "context_version text" in sql
    assert "output_path text" in sql
    assert "readiness_status text" in sql
    assert "manifest_document_count integer not null default 0" in sql
    assert "official_reference_count integer not null default 0" in sql
    assert "missing_files jsonb not null default '[]'::jsonb" in sql
    assert "extra_files jsonb not null default '[]'::jsonb" in sql
    assert "errors jsonb not null default '[]'::jsonb" in sql


def test_source_pack_import_runs_rls_and_indexes() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "alter table public.source_pack_import_runs enable row level security" in sql
    assert "public.is_workspace_member(workspace_id)" in sql
    assert "idx_source_pack_import_runs_workspace_id" in sql
    assert "idx_source_pack_import_runs_pack" in sql
    assert "idx_source_pack_import_runs_status" in sql
```

- [ ] **Step 2: Run RED**

Run:

```powershell
uv run --cache-dir .uv-cache pytest tests\integrity\test_source_pack_import_runs_migration.py -q
```

Expected: FAIL because `046_source_pack_import_runs.sql` does not exist.

- [ ] **Step 3: Add the migration**

Create `supabase/migrations/046_source_pack_import_runs.sql`:

```sql
create table public.source_pack_import_runs (
  id uuid primary key default gen_random_uuid(),

  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  actor_user_id uuid references auth.users(id) on delete set null,

  source_pack_id text,
  source_pack_version text,
  source_dir text,
  input_hash text not null,

  status text not null check (status in ('preflighted', 'compiled', 'rejected', 'failed')),
  recommended_action text not null check (recommended_action in ('compile_as_source_pack', 'normal_ingest', 'reject')),

  bundle_hash text,
  context_version text,
  output_path text,
  readiness_status text check (readiness_status is null or readiness_status in ('ready', 'warning', 'blocked')),
  readiness_score integer check (readiness_score is null or (readiness_score >= 0 and readiness_score <= 100)),

  numbered_source_count integer not null default 0 check (numbered_source_count >= 0),
  csv_count integer not null default 0 check (csv_count >= 0),
  markdown_count integer not null default 0 check (markdown_count >= 0),
  manifest_document_count integer not null default 0 check (manifest_document_count >= 0),
  official_reference_count integer not null default 0 check (official_reference_count >= 0),

  missing_files jsonb not null default '[]'::jsonb,
  extra_files jsonb not null default '[]'::jsonb,
  warnings jsonb not null default '[]'::jsonb,
  errors jsonb not null default '[]'::jsonb,
  metadata jsonb not null default '{}'::jsonb,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index idx_source_pack_import_runs_workspace_id
on public.source_pack_import_runs(workspace_id);

create index idx_source_pack_import_runs_actor_user_id
on public.source_pack_import_runs(actor_user_id);

create index idx_source_pack_import_runs_input_hash
on public.source_pack_import_runs(workspace_id, input_hash);

create index idx_source_pack_import_runs_pack
on public.source_pack_import_runs(workspace_id, source_pack_id, source_pack_version);

create index idx_source_pack_import_runs_status
on public.source_pack_import_runs(workspace_id, status);

create index idx_source_pack_import_runs_created_at
on public.source_pack_import_runs(created_at);

create trigger trg_source_pack_import_runs_updated_at
before update on public.source_pack_import_runs
for each row execute function public.touch_updated_at();

alter table public.source_pack_import_runs enable row level security;

create policy source_pack_import_runs_select_member
on public.source_pack_import_runs
for select
using (public.is_workspace_member(workspace_id));

create policy source_pack_import_runs_insert_member
on public.source_pack_import_runs
for insert
with check (public.is_workspace_member(workspace_id));

create policy source_pack_import_runs_update_manager
on public.source_pack_import_runs
for update
using (public.has_workspace_role(workspace_id, array['owner','manager']::workspace_role[]))
with check (public.has_workspace_role(workspace_id, array['owner','manager']::workspace_role[]));
```

- [ ] **Step 4: Run GREEN**

Run:

```powershell
uv run --cache-dir .uv-cache pytest tests\integrity\test_source_pack_import_runs_migration.py -q
```

Expected: PASS.

- [ ] **Step 5: Update data docs**

In `docs/04-data/DATA_MODEL.md`, add `source_pack_import_runs` to the table list with:

```markdown
| `source_pack_import_runs` | `046` | Source pack preflight/compile lifecycle and bundle hashes |
```

- [ ] **Step 6: Verify**

Run:

```powershell
uv run --cache-dir .uv-cache pytest tests\integrity\test_source_pack_import_runs_migration.py -q
uv run --cache-dir .uv-cache ruff check tests\integrity\test_source_pack_import_runs_migration.py
```

Expected: PASS / All checks passed.

## Task 2: Pydantic Schemas

**Agent:** API Contract Agent

**Files:**

- Create: `apps/api/src/context_builder/schemas/source_pack_import.py`
- Test: `tests/api/test_source_pack_import_runs.py`

- [ ] **Step 1: Write failing schema tests**

Create `tests/api/test_source_pack_import_runs.py` with:

```python
from __future__ import annotations

from context_builder.schemas.source_pack_import import (
    SourcePackImportRunCreate,
    SourcePackImportRunResponse,
    SourcePackImportRunUpdate,
)
from pydantic import ValidationError


def test_source_pack_import_run_create_accepts_preflight_fields() -> None:
    payload = SourcePackImportRunCreate(
        workspace_id="ws_1",
        actor_user_id="user_1",
        source_pack_id="compounding-pharmacy-gold-source-pack",
        source_pack_version="2026-05-25.v4",
        source_dir="C:/tmp/context-builder-sources/compounding-pharmacy-gold",
        input_hash="sha256:pack-input",
        status="preflighted",
        recommended_action="compile_as_source_pack",
        numbered_source_count=64,
        csv_count=39,
        markdown_count=25,
        manifest_document_count=64,
        official_reference_count=15,
        missing_files=[],
        extra_files=[],
        errors=[],
    )

    assert payload.status == "preflighted"
    assert payload.recommended_action == "compile_as_source_pack"


def test_source_pack_import_run_create_rejects_invalid_status() -> None:
    try:
        SourcePackImportRunCreate(
            workspace_id="ws_1",
            input_hash="sha256:pack-input",
            status="queued",
            recommended_action="compile_as_source_pack",
        )
    except ValidationError as exc:
        assert "status" in str(exc)
    else:
        raise AssertionError("expected ValidationError")


def test_source_pack_import_run_update_accepts_compile_result() -> None:
    payload = SourcePackImportRunUpdate(
        status="compiled",
        bundle_hash="abc123",
        context_version="ctx_abc123",
        output_path="C:/tmp/out/context_bundle.v1.json",
        readiness_status="warning",
        readiness_score=86,
        warnings=["Synthetic inventory only"],
        errors=[],
    )

    assert payload.status == "compiled"
    assert payload.readiness_status == "warning"


def test_source_pack_import_run_response_exposes_audit_fields() -> None:
    response = SourcePackImportRunResponse(
        id="run_1",
        workspace_id="ws_1",
        actor_user_id="user_1",
        source_pack_id="pack",
        source_pack_version="v1",
        source_dir=None,
        input_hash="sha256:pack-input",
        status="rejected",
        recommended_action="reject",
        bundle_hash=None,
        context_version=None,
        output_path=None,
        readiness_status=None,
        readiness_score=None,
        numbered_source_count=1,
        csv_count=0,
        markdown_count=1,
        manifest_document_count=1,
        official_reference_count=0,
        missing_files=["x.md"],
        extra_files=[],
        warnings=[],
        errors=["missing manifest files: x.md"],
        metadata={},
        created_at="2026-05-25T00:00:00+00:00",
        updated_at="2026-05-25T00:00:00+00:00",
    )

    assert response.id == "run_1"
    assert response.missing_files == ["x.md"]
```

- [ ] **Step 2: Run RED**

Run:

```powershell
uv run --cache-dir .uv-cache pytest tests\api\test_source_pack_import_runs.py -q
```

Expected: FAIL because `context_builder.schemas.source_pack_import` does not exist.

- [ ] **Step 3: Add schemas**

Create `apps/api/src/context_builder/schemas/source_pack_import.py`:

```python
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ImportRunStatus = Literal["preflighted", "compiled", "rejected", "failed"]
RecommendedAction = Literal["compile_as_source_pack", "normal_ingest", "reject"]
ReadinessStatus = Literal["ready", "warning", "blocked"]


class SourcePackImportRunCreate(BaseModel):
    model_config = ConfigDict(strict=True)

    workspace_id: str
    actor_user_id: str | None = None
    source_pack_id: str | None = None
    source_pack_version: str | None = None
    source_dir: str | None = None
    input_hash: str
    status: ImportRunStatus
    recommended_action: RecommendedAction
    bundle_hash: str | None = None
    context_version: str | None = None
    output_path: str | None = None
    readiness_status: ReadinessStatus | None = None
    readiness_score: int | None = Field(default=None, ge=0, le=100)
    numbered_source_count: int = Field(default=0, ge=0)
    csv_count: int = Field(default=0, ge=0)
    markdown_count: int = Field(default=0, ge=0)
    manifest_document_count: int = Field(default=0, ge=0)
    official_reference_count: int = Field(default=0, ge=0)
    missing_files: list[str] = Field(default_factory=list)
    extra_files: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourcePackImportRunUpdate(BaseModel):
    model_config = ConfigDict(strict=True)

    status: ImportRunStatus
    bundle_hash: str | None = None
    context_version: str | None = None
    output_path: str | None = None
    readiness_status: ReadinessStatus | None = None
    readiness_score: int | None = Field(default=None, ge=0, le=100)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourcePackImportRunResponse(SourcePackImportRunCreate):
    id: str
    created_at: str
    updated_at: str
```

- [ ] **Step 4: Run GREEN**

Run:

```powershell
uv run --cache-dir .uv-cache pytest tests\api\test_source_pack_import_runs.py -q
uv run --cache-dir .uv-cache ruff check apps\api\src\context_builder\schemas\source_pack_import.py tests\api\test_source_pack_import_runs.py
```

Expected: PASS / All checks passed.

## Task 3: Import Run Service

**Agent:** Persistence Service Agent

**Files:**

- Create: `apps/api/src/context_builder/services/source_pack_import_runs.py`
- Modify: `tests/api/test_source_pack_import_runs.py`

- [ ] **Step 1: Add fake DB and failing service tests**

Merge the new imports into the top import block in `tests/api/test_source_pack_import_runs.py`, then append the fake DB helpers and tests:

```python
from pathlib import Path
from typing import Any

from context_builder.schemas.source import SourcePackPreflightResponse
from context_builder.services.source_pack_import_runs import (
    create_import_run_from_preflight,
    source_pack_input_hash,
    update_import_run_compiled,
)


class Result:
    def __init__(self, data: Any) -> None:
        self.data = data


class Query:
    def __init__(self, db: "ImportRunDB", table: str) -> None:
        self.db = db
        self.table = table
        self.payload: dict[str, Any] = {}
        self.filters: dict[str, Any] = {}

    def insert(self, payload: dict[str, Any]) -> "Query":
        self.payload = payload
        return self

    def update(self, payload: dict[str, Any]) -> "Query":
        self.payload = payload
        return self

    def eq(self, field: str, value: Any) -> "Query":
        self.filters[field] = value
        return self

    def execute(self) -> Result:
        if self.table != "source_pack_import_runs":
            raise AssertionError(self.table)
        if self.payload and self.filters:
            row = {**self.db.rows[0], **self.payload}
            self.db.rows[0] = row
            return Result([row])
        if self.payload:
            row = {
                "id": "run_1",
                "created_at": "2026-05-25T00:00:00+00:00",
                "updated_at": "2026-05-25T00:00:00+00:00",
                **self.payload,
            }
            self.db.rows.append(row)
            return Result([row])
        return Result([])


class ImportRunDB:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def table(self, name: str) -> Query:
        return Query(self, name)


def _complete_preflight() -> SourcePackPreflightResponse:
    return SourcePackPreflightResponse(
        is_source_pack=True,
        status="complete",
        recommended_action="compile_as_source_pack",
        source_pack_id="compounding-pharmacy-gold-source-pack",
        source_pack_version="2026-05-25.v4",
        language="pt-BR",
        publication_status="source_seed",
        numbered_source_count=64,
        csv_count=39,
        markdown_count=25,
        manifest_document_count=64,
        official_reference_count=15,
        readme_present=True,
        missing_files=[],
        extra_files=[],
        errors=[],
    )


def _pack_dir(tmp_path: Path) -> Path:
    source_dir = tmp_path / "pack"
    source_dir.mkdir()
    (source_dir / "00_source_manifest.md").write_text("version: 1\n", encoding="utf-8")
    (source_dir / "01_policy.md").write_text("hello\n", encoding="utf-8")
    return source_dir


def test_create_import_run_from_complete_preflight(tmp_path: Path) -> None:
    db = ImportRunDB()
    source_dir = _pack_dir(tmp_path)

    run = create_import_run_from_preflight(
        db,
        workspace_id="ws_1",
        actor_user_id="user_1",
        source_dir=str(source_dir),
        preflight=_complete_preflight(),
    )

    assert run.id == "run_1"
    assert run.status == "preflighted"
    assert run.recommended_action == "compile_as_source_pack"
    assert run.input_hash.startswith("sha256:")
    assert db.rows[0]["source_pack_id"] == "compounding-pharmacy-gold-source-pack"
    assert db.rows[0]["manifest_document_count"] == 64


def test_create_import_run_from_rejected_preflight(tmp_path: Path) -> None:
    db = ImportRunDB()
    source_dir = _pack_dir(tmp_path)
    preflight = _complete_preflight().model_copy(
        update={
            "status": "incomplete",
            "recommended_action": "reject",
            "missing_files": ["40_quote_rules_matrix.csv"],
        }
    )

    run = create_import_run_from_preflight(
        db,
        workspace_id="ws_1",
        actor_user_id="user_1",
        source_dir=str(source_dir),
        preflight=preflight,
    )

    assert run.status == "rejected"
    assert run.errors == ["missing_files"]
    assert run.missing_files == ["40_quote_rules_matrix.csv"]


def test_update_import_run_compiled_sets_bundle_fields(tmp_path: Path) -> None:
    db = ImportRunDB()
    source_dir = _pack_dir(tmp_path)
    create_import_run_from_preflight(
        db,
        workspace_id="ws_1",
        actor_user_id="user_1",
        source_dir=str(source_dir),
        preflight=_complete_preflight(),
    )

    run = update_import_run_compiled(
        db,
        run_id="run_1",
        bundle_hash="abc123",
        context_version="ctx_abc123",
        output_path="C:/tmp/out/context_bundle.v1.json",
        readiness_status="warning",
        readiness_score=86,
        warnings=["Synthetic inventory only"],
    )

    assert run.status == "compiled"
    assert run.bundle_hash == "abc123"
    assert run.output_path == "C:/tmp/out/context_bundle.v1.json"
    assert run.readiness_status == "warning"


def test_source_pack_input_hash_is_content_based(tmp_path: Path) -> None:
    source_dir = _pack_dir(tmp_path)

    first_hash = source_pack_input_hash(source_dir)
    second_hash = source_pack_input_hash(source_dir)
    (source_dir / "01_policy.md").write_text("changed\n", encoding="utf-8")
    changed_hash = source_pack_input_hash(source_dir)

    assert first_hash == second_hash
    assert first_hash.startswith("sha256:")
    assert changed_hash != first_hash
```

- [ ] **Step 2: Run RED**

Run:

```powershell
uv run --cache-dir .uv-cache pytest tests\api\test_source_pack_import_runs.py -q
```

Expected: FAIL because service functions do not exist.

- [ ] **Step 3: Implement service**

Create `apps/api/src/context_builder/services/source_pack_import_runs.py`:

```python
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Protocol, cast

from context_builder.schemas.source import SourcePackPreflightResponse
from context_builder.schemas.source_pack_import import SourcePackImportRunResponse


class TableQuery(Protocol):
    def insert(self, payload: dict[str, Any]) -> "TableQuery": ...
    def update(self, payload: dict[str, Any]) -> "TableQuery": ...
    def eq(self, field: str, value: Any) -> "TableQuery": ...
    def execute(self) -> Any: ...


class TableClient(Protocol):
    def table(self, name: str) -> TableQuery: ...


def create_import_run_from_preflight(
    db: TableClient,
    *,
    workspace_id: str,
    actor_user_id: str | None,
    source_dir: str,
    preflight: SourcePackPreflightResponse,
) -> SourcePackImportRunResponse:
    status = "preflighted" if preflight.recommended_action != "reject" else "rejected"
    errors: list[str] = []
    if preflight.missing_files:
        errors.append("missing_files")
    if preflight.extra_files:
        errors.append("extra_files")
    errors.extend(preflight.errors)
    payload = {
        "workspace_id": workspace_id,
        "actor_user_id": actor_user_id,
        "source_pack_id": preflight.source_pack_id,
        "source_pack_version": preflight.source_pack_version,
        "source_dir": source_dir,
        "input_hash": source_pack_input_hash(Path(source_dir)),
        "status": status,
        "recommended_action": preflight.recommended_action,
        "bundle_hash": None,
        "context_version": None,
        "output_path": None,
        "readiness_status": None,
        "readiness_score": None,
        "numbered_source_count": preflight.numbered_source_count,
        "csv_count": preflight.csv_count,
        "markdown_count": preflight.markdown_count,
        "manifest_document_count": preflight.manifest_document_count,
        "official_reference_count": preflight.official_reference_count,
        "missing_files": preflight.missing_files,
        "extra_files": preflight.extra_files,
        "warnings": [],
        "errors": errors,
        "metadata": {
            "is_source_pack": preflight.is_source_pack,
            "preflight_status": preflight.status,
            "language": preflight.language,
            "publication_status": preflight.publication_status,
            "readme_present": preflight.readme_present,
        },
    }
    result = db.table("source_pack_import_runs").insert(payload).execute()
    return _response_from_result(result)


def update_import_run_compiled(
    db: TableClient,
    *,
    run_id: str,
    bundle_hash: str,
    context_version: str,
    output_path: str,
    readiness_status: str,
    readiness_score: int,
    warnings: list[str],
) -> SourcePackImportRunResponse:
    payload = {
        "status": "compiled",
        "bundle_hash": bundle_hash,
        "context_version": context_version,
        "output_path": output_path,
        "readiness_status": readiness_status,
        "readiness_score": readiness_score,
        "warnings": warnings,
        "errors": [],
    }
    result = (
        db.table("source_pack_import_runs")
        .update(payload)
        .eq("id", run_id)
        .execute()
    )
    return _response_from_result(result)


def _response_from_result(result: Any) -> SourcePackImportRunResponse:
    data = getattr(result, "data", None)
    if isinstance(data, list) and data:
        row = data[0]
    elif isinstance(data, dict):
        row = data
    else:
        raise RuntimeError("source_pack_import_run_write_failed")
    return SourcePackImportRunResponse(**cast(dict[str, Any], row))


def source_pack_input_hash(source_dir: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(path for path in source_dir.rglob("*") if path.is_file()):
        relative_path = path.relative_to(source_dir).as_posix()
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"
```

- [ ] **Step 4: Run GREEN**

Run:

```powershell
uv run --cache-dir .uv-cache pytest tests\api\test_source_pack_import_runs.py -q
uv run --cache-dir .uv-cache ruff check apps\api\src\context_builder\services\source_pack_import_runs.py tests\api\test_source_pack_import_runs.py
```

Expected: PASS / All checks passed.

## Task 4: Persist Runs From Preflight API

**Agent:** API Integration Agent

**Files:**

- Modify: `apps/api/src/context_builder/schemas/source.py`
- Modify: `apps/api/src/context_builder/routers/sources.py`
- Modify: `tests/api/test_source_pack_preflight.py`

- [ ] **Step 1: Add failing API test for persisted preflight**

Append to `tests/api/test_source_pack_preflight.py`:

```python
class Result:
    def __init__(self, data: Any) -> None:
        self.data = data


class Query:
    def __init__(self, db: "PreflightPersistDB", table: str) -> None:
        self.db = db
        self.table = table
        self.payload: dict[str, Any] = {}

    def insert(self, payload: dict[str, Any]) -> "Query":
        self.payload = payload
        return self

    def execute(self) -> Result:
        assert self.table == "source_pack_import_runs"
        row = {
            "id": "run_1",
            "created_at": "2026-05-25T00:00:00+00:00",
            "updated_at": "2026-05-25T00:00:00+00:00",
            **self.payload,
        }
        self.db.rows.append(row)
        return Result([row])


class PreflightPersistDB:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def table(self, name: str) -> Query:
        return Query(self, name)


@pytest.mark.skipif(not GOLD_DIR.exists(), reason="gold source pack not present")
def test_source_pack_preflight_can_persist_import_run(monkeypatch: pytest.MonkeyPatch) -> None:
    db = PreflightPersistDB()
    client = _client(monkeypatch, db=db)

    response = client.post(
        "/workspaces/ws_1/sources/source-pack/preflight",
        json={"source_dir": str(GOLD_DIR), "persist": True},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["import_run_id"] == "run_1"
    assert db.rows[0]["status"] == "preflighted"
    assert db.rows[0]["recommended_action"] == "compile_as_source_pack"
```

Update `_client` helper signature in that test file to accept `db: object | None = None` and override `get_supabase_service_for_backend_only` with `db`.

- [ ] **Step 2: Run RED**

Run:

```powershell
uv run --cache-dir .uv-cache pytest tests\api\test_source_pack_preflight.py::test_source_pack_preflight_can_persist_import_run -q
```

Expected: FAIL because request schema lacks `persist`, response lacks `import_run_id`, and router does not insert.

- [ ] **Step 3: Extend request/response schema**

Modify `apps/api/src/context_builder/schemas/source.py`:

```python
class SourcePackPreflightRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    source_dir: str
    persist: bool = False
```

Add to `SourcePackPreflightResponse`:

```python
    import_run_id: str | None = None
```

- [ ] **Step 4: Persist from router**

Modify `apps/api/src/context_builder/routers/sources.py`:

```python
from context_builder.services.source_pack_import_runs import create_import_run_from_preflight
```

Update route dependencies:

```python
async def preflight_source_pack_upload(
    payload: SourcePackPreflightRequest,
    membership: dict[str, Any] = Depends(require_upload_permission),
    db: Client = Depends(get_supabase_service_for_backend_only),
) -> SourcePackPreflightResponse:
```

Implementation:

```python
    response = inspect_source_pack_upload(Path(payload.source_dir))
    if payload.persist:
        run = create_import_run_from_preflight(
            db,
            workspace_id=membership["workspace_id"],
            actor_user_id=membership["user"]["id"],
            source_dir=payload.source_dir,
            preflight=response,
        )
        response = response.model_copy(update={"import_run_id": run.id})
    return response
```

- [ ] **Step 5: Run GREEN**

Run:

```powershell
uv run --cache-dir .uv-cache pytest tests\api\test_source_pack_preflight.py -q
```

Expected: PASS.

## Task 5: Docs And Task Record

**Agent:** Documentation Agent

**Files:**

- Create: `tasks/TASK-019-source-pack-import-run-persistence.md`
- Modify: `docs/operations/source-pack-compiler-runbook.md`
- Modify: `docs/07-qa/ACCEPTANCE_CRITERIA.md`

- [ ] **Step 1: Add task record**

Create `tasks/TASK-019-source-pack-import-run-persistence.md`:

```markdown
# TASK-019 - Source Pack Import Run Persistence

Status: implemented locally, pending real Supabase smoke.

## Goal

Persist every source-pack preflight and compile lifecycle event as an auditable
workspace-scoped import run.

## Implemented

- Migration `046_source_pack_import_runs.sql`
- Pydantic schemas for import run create/update/response
- Service to create preflight runs and update compiled runs
- Optional `persist` flag on source-pack preflight API
- `import_run_id` returned when persistence is requested
- Deterministic `input_hash` for source-pack directory contents

## Remaining Product Work

- Compile API should update the persisted run to `compiled` or `failed`
- ZIP/folder upload should create import runs automatically
- Console should show import-run history and latest bundle hash
- Real Supabase smoke should verify RLS and audit access
```

- [ ] **Step 2: Update runbook**

In `docs/operations/source-pack-compiler-runbook.md`, add:

```markdown
To persist a preflight run, pass:

```json
{
  "source_dir": "C:\\tmp\\context-builder-sources\\compounding-pharmacy-gold",
  "persist": true
}
```

The response includes `import_run_id`.
```

- [ ] **Step 3: Update acceptance criteria**

In `docs/07-qa/ACCEPTANCE_CRITERIA.md`, under Source Pack Compiler add:

```markdown
- [ ] Source pack preflight/compile lifecycle cria `source_pack_import_runs` com workspace, actor, source_pack_id/version, recommended_action, status, counts, missing/extra files e bundle hash quando aplicavel
- [ ] Cada source pack import run registra `input_hash` deterministico para correlacionar preflight, compile e import sem depender apenas de path local
```

- [ ] **Step 4: Verify docs**

Run:

```powershell
uv run --cache-dir .uv-cache ruff check tests\api\test_source_pack_preflight.py tests\api\test_source_pack_import_runs.py
git diff --check
```

Expected: PASS / no whitespace errors.

## Task 6: Full Gates And Commit

**Agent:** Controller

**Files:** all changed files.

- [ ] **Step 1: Run focused gates**

Run:

```powershell
uv run --cache-dir .uv-cache pytest tests\integrity\test_source_pack_import_runs_migration.py tests\api\test_source_pack_import_runs.py tests\api\test_source_pack_preflight.py -q
uv run --cache-dir .uv-cache ruff check .
npm run typecheck:python
npm run typecheck:python:strict-full
uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py
```

Expected:

```text
all tests pass
All checks passed!
Success: no issues found
secret scan exit 0
```

- [ ] **Step 2: Run full test suite**

Run:

```powershell
uv run --cache-dir .uv-cache pytest -q
```

Expected: PASS.

- [ ] **Step 3: Review changed files**

Run:

```powershell
git status --short --branch
git diff --stat
git diff --check
```

Expected: only intended files changed, no whitespace errors.

- [ ] **Step 4: Commit**

Run:

```powershell
git add supabase\migrations\046_source_pack_import_runs.sql apps\api\src\context_builder\schemas\source_pack_import.py apps\api\src\context_builder\services\source_pack_import_runs.py apps\api\src\context_builder\schemas\source.py apps\api\src\context_builder\routers\sources.py tests\integrity\test_source_pack_import_runs_migration.py tests\api\test_source_pack_import_runs.py tests\api\test_source_pack_preflight.py docs\04-data\DATA_MODEL.md docs\operations\source-pack-compiler-runbook.md docs\07-qa\ACCEPTANCE_CRITERIA.md tasks\TASK-019-source-pack-import-run-persistence.md
git commit -m "feat: persist source pack import runs"
```

Expected: commit created.

## Acceptance Criteria

- Preflight can run without persistence exactly as today.
- Preflight with `persist=true` creates one `source_pack_import_runs` row.
- Complete source packs persist `status = preflighted` and `recommended_action = compile_as_source_pack`.
- Incomplete source packs persist `status = rejected`, missing files and errors.
- Every persisted run includes deterministic `input_hash`.
- Compile result service can update a run to `compiled` with `bundle_hash`, `context_version`, `output_path`, readiness and warnings.
- Migration is RLS-enabled and workspace-scoped.
- Full local suite, lint, typechecks and secret scan pass.

## Self-Review

- Spec coverage: The plan covers schema, migration, persistence service, API integration, docs and gates.
- Placeholder scan: No TBD/TODO placeholders remain.
- Type consistency: `SourcePackPreflightResponse.import_run_id`, `SourcePackImportRunResponse.id`, and service return types match across tasks.
