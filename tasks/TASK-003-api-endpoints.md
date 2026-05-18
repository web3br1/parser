# TASK-003 — FastAPI API (Upload + Workspace + Auth)

**Projeto:** Context Builder Empresarial  
**Status:** `ready`  
**Versão:** 2.0 (hardening aplicado — 12 gaps fechados)  
**Agente:** Claude Code / Codex  
**Estimativa:** 1–2 sessões  
**Depende de:** TASK-001 ✅, TASK-002 ✅  
**Bloqueia:** TASK-006 (review endpoints), TASK-008 (query endpoint)  
**Emenda:** TASK-002 (ajuste de `file_path` → `storage_path` — ver seção abaixo)

---

## Objetivo

Implementar a camada API FastAPI que recebe uploads de arquivo, cria workspaces e fontes, e dispara o pipeline de ingestão. Esta é a porta de entrada do sistema — tudo o que acontece nos workers depende do que a API persiste.

Escopo desta task:

```
Browser → [TASK-003] POST /workspaces/{id}/sources/upload
  → auth check (Bearer JWT)
  → role check (owner | manager only)
  → file validation (security package)
  → Supabase Storage upload
  → source record (status=uploaded)
  → processing_job (status=queued, idempotency_key)
  → ingest_source.delay(storage_path=...)
  → return {source_id, job_id}
       [TASK-002] worker-ingest ←
```

**Não implementar** endpoints de revisão, publicação ou consulta. Estes são TASK-006, TASK-007 e TASK-008.

---

## Decisões fechadas

### Storage path canônico

```
workspaces/{workspace_id}/sources/{source_id}/original{suffix}
```

Nunca usar o nome original do arquivo no path de storage. O nome original fica em `sources.original_filename`. Isso elimina riscos de path traversal e caracteres especiais.

### Role mínimo para upload

`owner` ou `manager`. `staff` e `reviewer` não podem fazer upload. Validar na rota, não apenas no middleware.

### Falha parcial no upload

Se qualquer passo após a criação da source falhar, aplicar rollback manual:

```
source criada → storage falha → source.status = "failed"
source criada → storage ok → job_insert falha → delete_from_storage + source.status = "failed"
source criada → tudo ok → enqueue falha → job permanece queued (aceitável — scheduler re-enfileira)
```

O enqueue do Celery acontece **após** todos os writes no DB confirmarem. Se o `.delay()` falhar isoladamente, o job fica `queued` e pode ser re-enfileirado. Não é rollback de DB.

### Leitura do arquivo em memória

```
MVP: leitura completa via await file.read() — aceito até 50 MB.
V1: migrar para streaming com SpooledTemporaryFile para reduzir footprint de memória.
```

Documentar esta limitação em comentário no código.

### Idempotência do job de ingest

```python
idempotency_key = sha256(f"ingest:{source_id}:{file_hash}".encode()).hexdigest()
```

Inserir em `processing_jobs.idempotency_key` — campo `NOT NULL UNIQUE` no DDL.

---

## Emenda obrigatória à TASK-002

A TASK-002 implementou `ingest_source` com `file_path` como caminho local. Arquivos ficam no Supabase Storage. Correção obrigatória antes de integrar.

### Renomear parâmetro em `workers/ingest/src/worker_ingest/tasks.py`

```python
# ANTES
def ingest_source(self, *, job_id, source_id, workspace_id,
                  file_path: str, declared_mime: str, file_hash: str):

# DEPOIS
def ingest_source(self, *, job_id, source_id, workspace_id,
                  storage_path: str,    # ← renomeado
                  declared_mime: str, file_hash: str):
```

### Adicionar `workers/ingest/src/worker_ingest/storage.py`

```python
import os
import tempfile
from pathlib import Path
from supabase import create_client


def download_from_storage(storage_path: str) -> str:
    """
    Baixa arquivo do Supabase Storage para /tmp.
    Retorna caminho local do arquivo temporário.
    Caller é responsável por deletar o arquivo no finally.
    Nunca logar o conteúdo (data) do arquivo.
    """
    supabase = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )
    bucket  = os.environ["WORKSPACE_STORAGE_BUCKET"]
    data    = supabase.storage.from_(bucket).download(storage_path)
    suffix  = Path(storage_path).suffix or ".tmp"
    tmp     = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir="/tmp")
    tmp.write(data)
    tmp.flush()
    tmp.close()
    return tmp.name
```

### Atualizar passo 3 do fluxo no `tasks.py`

```python
local_path = download_from_storage(storage_path)
try:
    validation = validate_file(Path(local_path), declared_mime)
    # ... resto do fluxo usando local_path
finally:
    Path(local_path).unlink(missing_ok=True)
```

---

## Arquivos a criar ou modificar

```
apps/api/
  src/context_builder/
    main.py            ← implementar app factory + routers + error handlers
    config.py          ← implementar Settings com pydantic-settings
    dependencies.py    ← auth, db clients, membership, role check
    routers/
      health.py
      workspaces.py
      sources.py
    schemas/
      workspace.py
      source.py
      job.py
    services/
      storage.py       ← upload_to_storage(), delete_from_storage()
      ingest_queue.py  ← create_and_enqueue_ingest_job()

workers/ingest/
  src/worker_ingest/
    storage.py         ← novo: download_from_storage()
    tasks.py           ← atualizar: storage_path em vez de file_path

tests/
  api/
    test_health.py
    test_workspaces.py
    test_sources_upload.py
```

---

## `apps/api` — Config

Arquivo: `apps/api/src/context_builder/config.py`

```python
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Supabase
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str

    # Storage
    workspace_storage_bucket: str = "context-builder-private"

    # Redis / Celery
    redis_url: str = "redis://localhost:6379/0"

    # App
    app_env: str = "development"
    log_level: str = "INFO"

    # CORS — em produção, definir via env var
    cors_allowed_origins: list[str] = []

    # Upload limits
    max_file_size_bytes: int = 50 * 1024 * 1024   # 50 MB
    allowed_mime_types: list[str] = [
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "text/csv",
        "text/plain",
    ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

---

## `apps/api` — Dependencies

Arquivo: `apps/api/src/context_builder/dependencies.py`

```python
from datetime import datetime, timezone
from fastapi import Depends, HTTPException, Header
from supabase import create_client, Client
from .config import get_settings, Settings

UPLOAD_ALLOWED_ROLES: frozenset[str] = frozenset({"owner", "manager"})


def get_supabase_anon(settings: Settings = Depends(get_settings)) -> Client:
    """Client anon — valida JWT do usuário. Nunca usa service role."""
    return create_client(settings.supabase_url, settings.supabase_anon_key)


def get_supabase_service(settings: Settings = Depends(get_settings)) -> Client:
    """
    Client service role — operações privilegiadas no backend.
    NUNCA expor ao browser nem retornar ao cliente.
    """
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


async def get_current_user(
    authorization: str = Header(...),
    db: Client = Depends(get_supabase_anon),
) -> dict:
    """
    Extrai e valida JWT do header Authorization: Bearer <token>.
    Retorna {"id": user_id, "email": email}.
    Lança 401 se inválido ou expirado.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing_bearer_token")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        user_response = db.auth.get_user(token)
        if not user_response.user:
            raise HTTPException(status_code=401, detail="invalid_token")
        return {"id": user_response.user.id, "email": user_response.user.email}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="invalid_token")


async def require_workspace_member(
    workspace_id: str,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_supabase_service),
) -> dict:
    """
    Verifica membership no workspace.
    Retorna {"user": ..., "role": ..., "workspace_id": ...}.
    Lança 403 se não membro. Não revela se workspace existe para não-membros.
    """
    result = (
        db.table("workspace_members")
        .select("role")
        .eq("workspace_id", workspace_id)
        .eq("user_id", current_user["id"])
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=403, detail="not_workspace_member")
    return {
        "user": current_user,
        "role": result.data["role"],
        "workspace_id": workspace_id,
    }


async def require_upload_permission(
    membership: dict = Depends(require_workspace_member),
) -> dict:
    """
    Verifica que o membro tem role para fazer upload (owner | manager).
    staff e reviewer não têm permissão de upload.
    """
    if membership["role"] not in UPLOAD_ALLOWED_ROLES:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "insufficient_role",
                "required": list(UPLOAD_ALLOWED_ROLES),
                "current": membership["role"],
            },
        )
    return membership
```

---

## `apps/api` — App Factory

Arquivo: `apps/api/src/context_builder/main.py`

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from .config import get_settings
from .routers import health, workspaces, sources


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup: verificar variáveis obrigatórias
    settings = get_settings()
    assert settings.supabase_url, "SUPABASE_URL não configurado"
    assert settings.supabase_service_role_key, "SUPABASE_SERVICE_ROLE_KEY não configurado"
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Context Builder API",
        version="0.1.0",
        docs_url="/docs" if settings.app_env != "production" else None,
        redoc_url=None,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.app_env == "development" else settings.cors_allowed_origins,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request, exc):
        return JSONResponse(
            status_code=422,
            content={"detail": "validation_error", "errors": exc.errors()},
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request, exc):
        from fastapi import HTTPException as _HTTPException
        # HTTPException já tem handler próprio — não mascarar como 500
        if isinstance(exc, _HTTPException):
            raise exc
        import logging
        # Logar tipo do erro, nunca conteúdo sensível
        logging.getLogger("api").error("unhandled_exception type=%s", type(exc).__name__)
        return JSONResponse(
            status_code=500,
            content={"detail": "internal_server_error"},
        )

    app.include_router(health.router)
    app.include_router(workspaces.router, prefix="/workspaces", tags=["workspaces"])
    app.include_router(
        sources.router,
        prefix="/workspaces/{workspace_id}/sources",
        tags=["sources"],
    )
    return app


app = create_app()
```

---

## `apps/api` — Schemas

### `schemas/workspace.py`

```python
from pydantic import BaseModel
from datetime import datetime


class WorkspaceCreate(BaseModel):
    name: str
    slug: str | None = None


class WorkspaceResponse(BaseModel):
    id: str
    name: str
    slug: str | None
    status: str
    created_at: datetime
```

### `schemas/source.py`

```python
from pydantic import BaseModel
from datetime import datetime


class SourceResponse(BaseModel):
    id: str
    workspace_id: str
    status: str
    title: str | None
    original_filename: str | None
    mime_type: str | None
    file_size_bytes: int | None
    created_at: datetime


class UploadResponse(BaseModel):
    source_id: str
    job_id: str
    status: str       # "queued"
    message: str
```

### `schemas/job.py`

```python
from pydantic import BaseModel
from datetime import datetime


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    source_id: str
    started_at: datetime | None
    finished_at: datetime | None
    error_message: str | None   # campo correto conforme DDL (não "error")
    chunks_created: int | None
```

---

## `apps/api` — Routers

### `routers/health.py`

```python
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}
```

### `routers/workspaces.py`

```python
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from supabase import Client
from ..dependencies import get_current_user, get_supabase_service
from ..schemas.workspace import WorkspaceCreate, WorkspaceResponse

router = APIRouter()


@router.post("", response_model=WorkspaceResponse, status_code=201)
async def create_workspace(
    body: WorkspaceCreate,
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_supabase_service),
) -> WorkspaceResponse:
    """
    Cria workspace e adiciona o criador como owner.
    Os dois inserts não são transacionais no Supabase client —
    se o segundo falhar, o workspace fica sem owner.
    Mitigação MVP: RLS bloqueia acesso a workspace sem membership.

    DÍVIDA V1 OBRIGATÓRIA: substituir pelos dois inserts por uma RPC Postgres:
        supabase.rpc("create_workspace_with_owner", {...}).execute()
    A função deve executar ambos os inserts em uma única transaction no banco.
    """
    ws_result = (
        db.table("workspaces")
        .insert({
            "name": body.name,
            "slug": body.slug,
            "created_by": current_user["id"],
        })
        .execute()
    )
    workspace = ws_result.data[0]

    db.table("workspace_members").insert({
        "workspace_id": workspace["id"],
        "user_id": current_user["id"],
        "role": "owner",
        "joined_at": datetime.now(timezone.utc).isoformat(),   # ← ISO string, não "now()"
    }).execute()

    return WorkspaceResponse(**workspace)


@router.get("", response_model=list[WorkspaceResponse])
async def list_workspaces(
    current_user: dict = Depends(get_current_user),
    db: Client = Depends(get_supabase_service),
) -> list[WorkspaceResponse]:
    result = (
        db.table("workspace_members")
        .select("workspace_id, workspaces(*)")
        .eq("user_id", current_user["id"])
        .execute()
    )
    return [WorkspaceResponse(**row["workspaces"]) for row in result.data]
```

### `routers/sources.py`

```python
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from supabase import Client
from ..dependencies import require_workspace_member, require_upload_permission, get_supabase_service, get_settings
from ..schemas.source import SourceResponse, UploadResponse
from ..schemas.job import JobStatusResponse
from ..services.storage import upload_to_storage, delete_from_storage
from ..services.ingest_queue import create_and_enqueue_ingest_job
from security.file_validator import validate_file
import tempfile

router = APIRouter()


@router.post("/upload", response_model=UploadResponse, status_code=202)
async def upload_source(
    file: UploadFile = File(...),
    membership: dict = Depends(require_upload_permission),   # owner | manager only
    db: Client = Depends(get_supabase_service),
) -> UploadResponse:
    workspace_id = membership["workspace_id"]
    user_id      = membership["user"]["id"]
    settings     = get_settings()

    # MVP: leitura completa em memória. Limite 50 MB.
    # V1: migrar para streaming com SpooledTemporaryFile.
    content = await file.read()
    if len(content) > settings.max_file_size_bytes:
        raise HTTPException(status_code=413, detail="file_too_large")

    file_hash = hashlib.sha256(content).hexdigest()

    # Deduplicação por hash dentro do workspace
    existing = (
        db.table("sources")
        .select("id, status")
        .eq("workspace_id", workspace_id)
        .eq("file_hash", file_hash)
        .maybe_single()
        .execute()
    )
    if existing.data:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "duplicate_file",
                "existing_source_id": existing.data["id"],
                "existing_status": existing.data["status"],
            },
        )

    # Validar arquivo via security package (temp em /tmp, deletar no finally)
    declared_mime = file.content_type or "application/octet-stream"
    original_name = file.filename or "upload"
    suffix = Path(original_name).suffix or ""

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)
    try:
        validation = validate_file(tmp_path, declared_mime)
    finally:
        tmp_path.unlink(missing_ok=True)

    if not validation.valid:
        raise HTTPException(
            status_code=422,
            detail={"code": "file_validation_failed", "reason": validation.reason},
        )

    detected_mime = validation.detected_mime or declared_mime

    # Criar source com status=uploaded
    source_result = (
        db.table("sources")
        .insert({
            "workspace_id": workspace_id,
            "type": "upload",
            "status": "uploaded",
            "original_filename": original_name,
            "mime_type": detected_mime,
            "file_size_bytes": len(content),
            "file_hash": file_hash,
            "uploaded_by": user_id,
        })
        .execute()
    )
    source_id = source_result.data[0]["id"]

    # Storage path canônico: sem nome original, sem caracteres especiais
    storage_path = f"workspaces/{workspace_id}/sources/{source_id}/original{suffix}"

    # Upload + job com rollback manual em caso de falha
    try:
        upload_to_storage(
            content=content,
            path=storage_path,
            mime_type=detected_mime,
        )

        # Atualizar source com storage info
        db.table("sources").update({
            "storage_bucket": settings.workspace_storage_bucket,
            "storage_path": storage_path,
        }).eq("id", source_id).execute()

        # Criar job e enfileirar worker
        job_id = create_and_enqueue_ingest_job(
            source_id=source_id,
            workspace_id=workspace_id,
            storage_path=storage_path,
            declared_mime=detected_mime,
            file_hash=file_hash,
            db=db,
        )

    except Exception as exc:
        # Rollback manual: marcar source como failed + limpar storage se necessário
        try:
            delete_from_storage(storage_path)
        except Exception:
            pass  # storage pode não existir se falhou antes do upload
        db.table("sources").update({
            "status": "failed",
        }).eq("id", source_id).execute()
        raise HTTPException(status_code=500, detail="upload_pipeline_failed") from exc

    return UploadResponse(
        source_id=source_id,
        job_id=job_id,
        status="queued",
        message="File accepted. Processing started.",
    )


@router.get("", response_model=list[SourceResponse])
async def list_sources(
    membership: dict = Depends(require_workspace_member),
    db: Client = Depends(get_supabase_service),
) -> list[SourceResponse]:
    result = (
        db.table("sources")
        .select("*")
        .eq("workspace_id", membership["workspace_id"])
        .is_("deleted_at", "null")
        .order("created_at", desc=True)
        .execute()
    )
    return [SourceResponse(**row) for row in result.data]


@router.get("/{source_id}", response_model=SourceResponse)
async def get_source(
    source_id: str,
    membership: dict = Depends(require_workspace_member),
    db: Client = Depends(get_supabase_service),
) -> SourceResponse:
    result = (
        db.table("sources")
        .select("*")
        .eq("id", source_id)
        .eq("workspace_id", membership["workspace_id"])
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="source_not_found")
    return SourceResponse(**result.data)


@router.get("/{source_id}/job", response_model=JobStatusResponse)
async def get_source_job(
    source_id: str,
    membership: dict = Depends(require_workspace_member),
    db: Client = Depends(get_supabase_service),
) -> JobStatusResponse:
    """Retorna o processing_job de ingest mais recente para a source."""
    result = (
        db.table("processing_jobs")
        .select("*")
        .eq("source_id", source_id)
        .eq("workspace_id", membership["workspace_id"])   # ownership check duplo
        .eq("job_type", "ingest")
        .order("created_at", desc=True)
        .limit(1)
        .maybe_single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="job_not_found")
    job = result.data
    return JobStatusResponse(
        job_id=job["id"],
        status=job["status"],
        source_id=source_id,
        started_at=job.get("started_at"),
        finished_at=job.get("finished_at"),
        error_message=job.get("error_message"),     # ← campo correto conforme DDL
        chunks_created=job.get("metadata", {}).get("chunks_created"),
    )
```

---

## `apps/api` — Services

### `services/storage.py`

```python
import os
from fastapi import HTTPException
from supabase import create_client


def upload_to_storage(*, content: bytes, path: str, mime_type: str) -> str:
    """
    Faz upload para o bucket privado.
    Lança HTTPException 500 se falhar.
    Nunca logar content.
    """
    supabase = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )
    bucket = os.environ["WORKSPACE_STORAGE_BUCKET"]
    try:
        supabase.storage.from_(bucket).upload(
            path=path,
            file=content,
            file_options={"content-type": mime_type, "cache-control": "3600"},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail="storage_upload_failed") from exc
    return path


def delete_from_storage(path: str) -> None:
    """Remove arquivo do storage. Usado em rollback e hard delete."""
    supabase = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )
    bucket = os.environ["WORKSPACE_STORAGE_BUCKET"]
    supabase.storage.from_(bucket).remove([path])
```

### `services/ingest_queue.py`

```python
import os
from hashlib import sha256
from supabase import Client
from worker_ingest.tasks import ingest_source


def create_and_enqueue_ingest_job(
    *,
    source_id: str,
    workspace_id: str,
    storage_path: str,
    declared_mime: str,
    file_hash: str,
    db: Client,
) -> str:
    """
    Cria processing_job com status='queued' no DB, então enfileira o worker.

    Ordem obrigatória:
    1. Insert do job no DB (confirma antes do .delay)
    2. ingest_source.delay() após insert confirmado

    Se .delay() falhar após insert: job permanece 'queued'.
    Um scheduler periódico pode re-enfileirar jobs queued sem started_at.
    Isso não é outbox pattern formal — é enqueue-after-insert.
    """
    idempotency_key = sha256(
        f"ingest:{source_id}:{file_hash}".encode()
    ).hexdigest()

    job_result = (
        db.table("processing_jobs")
        .insert({
            "workspace_id": workspace_id,
            "source_id": source_id,
            "job_type": "ingest",
            "status": "queued",
            "idempotency_key": idempotency_key,
            "metadata": {
                "storage_path": storage_path,
                "declared_mime": declared_mime,
                "file_hash": file_hash,
                "chunks_created": None,    # preenchido pelo worker ao completar
            },
        })
        .execute()
    )
    job_id = job_result.data[0]["id"]

    # Enqueue após insert confirmado
    ingest_source.delay(
        job_id=job_id,
        source_id=source_id,
        workspace_id=workspace_id,
        storage_path=storage_path,
        declared_mime=declared_mime,
        file_hash=file_hash,
    )

    return job_id
```

---

## Dependências novas

### `apps/api/pyproject.toml`

```toml
[project]
name = "context-builder-api"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.111",
  "uvicorn[standard]>=0.29",
  "pydantic-settings>=2.2",
  "supabase>=2.4",
  "python-multipart>=0.0.9",
  "context-builder-security",
]
```

### `.env.example` — confirmar campos presentes

```dotenv
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
WORKSPACE_STORAGE_BUCKET=context-builder-private
REDIS_URL=redis://localhost:6379/0
APP_ENV=development
CORS_ALLOWED_ORIGINS=[]
```

---

## Testes obrigatórios

### `tests/api/test_health.py`

```
✓ GET /health → 200 {"status": "ok"} sem auth
```

### `tests/api/test_workspaces.py`

Mockar `get_current_user` e `get_supabase_service`:

```
✓ POST /workspaces sem Bearer → 401
✓ POST /workspaces com auth válido → 201 + workspace com id
✓ workspace_member inserido com role="owner" e joined_at como ISO string (não "now()")
✓ GET /workspaces → lista apenas workspaces do usuário autenticado
```

### `tests/api/test_sources_upload.py`

Mockar auth, membership, supabase, `upload_to_storage`, `delete_from_storage`, `ingest_source.delay`:

```
✓ POST /upload sem Bearer → 401
✓ POST /upload usuário não membro → 403
✓ POST /upload role=staff → 403 insufficient_role
✓ POST /upload role=reviewer → 403 insufficient_role
✓ POST /upload role=manager → 202 (permitido)
✓ POST /upload arquivo > 50MB → 413
✓ POST /upload fake.pdf (magic bytes errado) → 422 reason=magic_bytes_fail
✓ POST /upload extensão bloqueada → 422 reason=extension_blocked
✓ POST /upload arquivo duplicado no workspace → 409 com existing_source_id
✓ POST /upload válido → 202 com source_id + job_id
✓ POST /upload válido → storage_path = "workspaces/{ws}/sources/{src}/original{suffix}"
✓ POST /upload válido → ingest_source.delay chamado com storage_path (não file_path)
✓ POST /upload válido → processing_job com idempotency_key preenchido
✓ POST /upload válido → metadata.chunks_created = None no job criado
✓ POST /upload: storage falha → source.status="failed", delete_from_storage NÃO chamado (objeto não existe no bucket)
✓ POST /upload: job insert falha → source.status="failed", delete_from_storage chamado (upload já confirmado)
✓ GET /sources → apenas sources do workspace correto
✓ GET /sources/{id} de workspace diferente → 404 (não 403)
✓ GET /sources/{id}/job → job_status com error_message (não "error")
✓ stack trace nunca presente em response de erro (mock de Exception genérica)
✓ SUPABASE_SERVICE_ROLE_KEY nunca presente em response (verificar JSONResponse)
```

---

## O que NÃO fazer

- Não implementar endpoints de revisão (TASK-006).
- Não implementar endpoints de publicação (TASK-007).
- Não implementar query endpoint (TASK-008).
- Não expor `SUPABASE_SERVICE_ROLE_KEY` em resposta ou log.
- Não retornar stack trace ao cliente.
- Não armazenar arquivo localmente na API de forma permanente.
- Não usar `"now()"` como string em inserts — usar `datetime.now(timezone.utc).isoformat()`.
- Não chamar `ingest_source.delay()` dentro de try antes do insert do job confirmar.
- Não implementar rate limiting (infraestrutura — nginx/gateway).
- Não aceitar upload de `staff` ou `reviewer`.
- Não usar o nome original do arquivo no storage path — usar `original{suffix}`.
- Não chamar o padrão de "outbox" — é enqueue-after-insert. Não confundir os dois.

---

## Critérios de aceite

```
[ ] pytest tests/api/ -v → todos passam
[ ] GET /health → 200 sem auth
[ ] POST /workspaces sem Bearer → 401
[ ] POST /upload role=staff → 403
[ ] POST /upload arquivo com magic bytes errado → 422
[ ] POST /upload arquivo duplicado no workspace → 409
[ ] POST /upload válido → 202 com source_id + job_id
[ ] storage_path = "workspaces/{ws}/sources/{src}/original{suffix}" (sem nome original)
[ ] ingest_source.delay chamado com storage_path (mock — verificar kwarg)
[ ] idempotency_key em processing_jobs = sha256("ingest:{source_id}:{file_hash}") (teste unitário)
[ ] metadata.chunks_created = None no job criado (mock)
[ ] storage falha → source.status="failed" + delete_from_storage NÃO chamado (mock — storage_uploaded=False)
[ ] job insert falha → source.status="failed" + delete_from_storage chamado (mock — storage_uploaded=True)
[ ] joined_at é ISO string (não "now()") no workspace_member
[ ] GET /sources/{id} de workspace diferente → 404
[ ] JobStatusResponse usa error_message (não "error")
[ ] stack trace ausente em response de erro genérico (mock de Exception)
[ ] uvicorn context_builder.main:app --reload → inicia sem erro
[ ] ruff check apps/api → zero erros
[ ] mypy apps/api → zero erros
[ ] worker-ingest tasks.py usa storage_path em vez de file_path (grep)
[ ] workers/ingest/storage.py existe com download_from_storage()
```

---

## Referências

- `CLAUDE.md` — segurança, autenticação, princípios
- `docs/05-security/SECURITY.md` — validação de upload, isolamento de workers
- `docs/01-product/USER_FLOWS.md` — Fluxo 1 (upload e ingestão)
- `supabase/migrations/001_enums.sql` — job_status, workspace_role enums
- `supabase/migrations/002_workspaces.sql` — workspaces, workspace_members
- `supabase/migrations/004_sources.sql` — sources schema
- `supabase/migrations/016_jobs.sql` — processing_jobs, idempotency_key, error_message
- `TASK-002` — ingest worker (emenda de storage_path obrigatória)
