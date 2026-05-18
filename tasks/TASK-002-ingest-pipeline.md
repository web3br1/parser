# TASK-002 — Ingest Pipeline (Validate → Extract → Quality Gate → Chunk)

**Projeto:** Context Builder Empresarial  
**Status:** `ready`  
**Versão:** 2.0 (hardening aplicado — 15 gaps fechados)  
**Agente:** Claude Code / Codex  
**Estimativa:** 1–2 sessões  
**Depende de:** TASK-001 (monorepo scaffold) ✅  
**Bloqueia:** TASK-003 (API endpoints), TASK-004 (Celery classification worker)

---

## Objetivo

Implementar o pipeline de ingestão de ponta a ponta dentro do `worker-ingest`, cobrindo as etapas 2–5 do pipeline obrigatório:

```
[TASK-003] Upload → [TASK-002] File Validation → Text Extraction → Quality Gate → Chunking → [DB] store chunks
                                    ↑
                            esta task cobre isso
```

Ao final, um arquivo enviado ao worker deve resultar em chunks armazenados no PostgreSQL com status `pending`, prontos para classificação.

---

## Estrutura de arquivos a criar

```
packages/
  security/
    src/security/
      file_validator.py      ← substituir stub
    tests/
      test_file_validator.py

  parsers/
    pyproject.toml
    src/parsers/
      __init__.py            ← get_parser() aqui
      base.py                ← ExtractionError, ExtractionResult, BaseParser, sanitize_text
      pdf.py
      docx.py
      csv_parser.py
      xlsx_parser.py
      txt.py
      quality_gate.py
      chunker.py
    tests/
      fixtures/
        create_fixtures.py   ← script gerador
        good.pdf
        image_only.pdf
        good.docx
        good.csv
        semicolon.csv
        good.xlsx
        good.txt
        empty.txt
        fake.pdf
      test_pdf.py
      test_docx.py
      test_csv.py
      test_xlsx.py
      test_txt.py
      test_quality_gate.py
      test_chunker.py

workers/
  ingest/
    src/worker_ingest/
      tasks.py               ← ingest_source
      db.py                  ← funções de acesso ao DB (sem lógica de negócio)
      logging.py             ← logger estruturado
```

---

## `packages/security` — File Validator

Arquivo: `packages/security/src/security/file_validator.py`

### Interface obrigatória

```python
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class FileRejectionReason(StrEnum):
    MIME_MISMATCH      = "mime_mismatch"
    MAGIC_BYTES_FAIL   = "magic_bytes_fail"
    SIZE_EXCEEDED      = "size_exceeded"
    EXTENSION_BLOCKED  = "extension_blocked"
    EMPTY_FILE         = "empty_file"


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    reason: FileRejectionReason | None
    detected_mime: str | None
    file_size_bytes: int


def validate_file(path: Path, declared_mime: str) -> ValidationResult:
    ...
```

### Regras

| Verificação | Limite | Detalhe |
|---|---|---|
| Arquivo vazio | 0 bytes | verificar primeiro, antes de abrir |
| Tamanho máximo | 50 MB | rejeitar antes de abrir |
| Extensões permitidas | `.pdf .docx .csv .xlsx .txt` | rejeitar todo o resto |
| Magic bytes | obrigatório | usar `python-magic` |
| MIME declarado vs detectado | deve coincidir | ex: `.pdf` declarado → `application/pdf` detectado |

### Tabela de magic bytes

```python
MAGIC_MAP: dict[str, bytes | None] = {
    "application/pdf": b"%PDF",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": b"PK\x03\x04",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": b"PK\x03\x04",
    "text/csv": None,    # sem magic bytes — validar apenas MIME e extensão
    "text/plain": None,
}

ALLOWED_EXTENSIONS: set[str] = {".pdf", ".docx", ".xlsx", ".csv", ".txt"}
MAX_FILE_SIZE_BYTES: int = 50 * 1024 * 1024  # 50 MB
```

Ordem de verificação obrigatória: vazio → tamanho → extensão → magic bytes → MIME. Retornar na primeira falha.

---

## `packages/parsers` — Base

Arquivo: `packages/parsers/src/parsers/base.py`

### Tipos obrigatórios

```python
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from enum import StrEnum
from pathlib import Path


class ExtractionError(StrEnum):
    PAGES_EXCEEDED      = "pages_exceeded"
    ROWS_EXCEEDED       = "rows_exceeded"
    UNSUPPORTED_FORMAT  = "unsupported_format"
    EMPTY_CONTENT       = "empty_content"
    PARSE_FAILED        = "parse_failed"


@dataclass(frozen=True)
class ExtractedPage:
    page_number: int     # 1-indexed; 0 para DOCX (sem conceito de página)
    text: str
    char_count: int
    is_empty: bool       # True se char_count == 0


@dataclass(frozen=True)
class ExtractedSheet:
    sheet_name: str
    headers: list[str]
    rows: list[dict]     # [{header: value}] — células vazias → ""
    row_start: int       # linha real da planilha (1-indexed)
    row_end: int


@dataclass
class ExtractionResult:
    mime_type: str
    pages: list[ExtractedPage] = field(default_factory=list)
    sheets: list[ExtractedSheet] = field(default_factory=list)
    total_chars: int = 0
    error: ExtractionError | None = None
    warnings: list[str] = field(default_factory=list)


class BaseParser(ABC):
    @abstractmethod
    def extract(self, path: Path) -> ExtractionResult:
        ...


MAX_EXTRACTED_CHARS: int = 500_000  # 500k chars — limite global de memória
```

### `sanitize_text` — obrigatório em todos os parsers

```python
def sanitize_text(text: str) -> str:
    """Remove bytes inválidos e normaliza espaçamento."""
    return (
        text.encode("utf-8", errors="ignore")
        .decode("utf-8")
        .strip()
    )
```

`sanitize_text` deve ser chamada em **todo texto extraído**, em todos os parsers, antes de armazenar em `ExtractedPage.text` ou `ExtractedSheet.rows`.

---

## `packages/parsers` — Seleção de parser

Arquivo: `packages/parsers/src/parsers/__init__.py`

```python
from .pdf import PDFParser
from .docx import DOCXParser
from .csv_parser import CSVParser
from .xlsx_parser import XLSXParser
from .txt import TXTParser
from .base import BaseParser, ExtractionError


class UnsupportedMimeError(Exception):
    def __init__(self, mime: str) -> None:
        super().__init__(f"Unsupported MIME type: {mime!r}")
        self.mime = mime


_PARSER_MAP: dict[str, BaseParser] = {
    "application/pdf": PDFParser(),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": DOCXParser(),
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": XLSXParser(),
    "text/csv": CSVParser(),
    "text/plain": TXTParser(),
}


def get_parser(mime: str) -> BaseParser:
    """Retorna o parser para o MIME type informado.

    Raises:
        UnsupportedMimeError: se o MIME não for suportado.
    """
    if mime not in _PARSER_MAP:
        raise UnsupportedMimeError(mime)
    return _PARSER_MAP[mime]
```

`get_parser` é o **único ponto de seleção de parser** em todo o sistema. O worker nunca instancia parsers diretamente.

---

## `packages/parsers` — Implementações por tipo

### `pdf.py`

- Biblioteca: `pymupdf` (fitz)
- Limite: máximo 200 páginas → retornar `error=ExtractionError.PAGES_EXCEEDED` sem extrair nenhuma página
- Limite global: se `total_chars > MAX_EXTRACTED_CHARS` → truncar texto + `warnings.append("text_limit_reached")` — **não falhar**
- Cada página → `ExtractedPage` com `is_empty=True` se `char_count == 0`
- Aplicar `sanitize_text` em cada página
- Nunca usar OCR — página sem texto selecionável → `is_empty=True`, incluir no resultado (não descartar)
- Se `fitz.open()` lançar exceção → retornar `error=ExtractionError.PARSE_FAILED`

### `docx.py`

- Biblioteca: `python-docx`
- Extrair parágrafos e tabelas
- Tabelas: converter cada linha em `| col1 | col2 |` e inserir no texto da seção correspondente
- Headings: prefixar com `##` (nível 1) ou `###` (nível 2+)
- `page_number=0` para todo conteúdo (DOCX não tem páginas)
- Aplicar `sanitize_text` em cada parágrafo antes de concatenar
- Limite global: se `total_chars > MAX_EXTRACTED_CHARS` → truncar texto + `warnings.append("text_limit_reached")` — **não falhar**
- Se `Document()` lançar exceção → `error=ExtractionError.PARSE_FAILED`

### `csv_parser.py`

- Biblioteca: `csv` (stdlib)
- Detectar delimitador com `csv.Sniffer` nos primeiros 2048 bytes
- Limite: máximo 10.000 linhas → retornar `error=ExtractionError.ROWS_EXCEEDED`
- Encoding: tentar `utf-8`, fallback `latin-1`
- Aplicar `sanitize_text` em cada célula
- `sheet_name="sheet1"` (fixo para CSV)
- `row_start` e `row_end` são índices 1-based das linhas de dados (excluindo header)
- Células vazias → `""` (nunca `None`)

### `xlsx_parser.py`

- Biblioteca: `openpyxl` com `read_only=True, data_only=True`
- Limite: máximo 10.000 linhas por aba → `error=ExtractionError.ROWS_EXCEEDED` na primeira aba que exceder
- Limite: máximo 20 abas → ignorar abas acima do limite + `warnings.append("sheets_truncated")`
- Encoding: `openpyxl` retorna strings — aplicar `sanitize_text` em cada célula
- Cabeçalho: primeira linha não vazia de cada aba
- `sheet_name` = nome exato da aba no arquivo
- `row_start` e `row_end` são 1-based, relativas à planilha real (linha 1 = header)
- Células vazias → `""` (nunca `None`)

### `txt.py`

- Encoding: tentar `utf-8`, fallback `latin-1`
- Limite: máximo 1 MB de bytes lidos
- Aplicar `sanitize_text` no conteúdo completo
- Retornar como `ExtractedPage(page_number=1, text=conteúdo, char_count=len(conteúdo), is_empty=len(conteúdo)==0)`
- Se `is_empty=True` → retornar com `error=ExtractionError.EMPTY_CONTENT`

---

## `packages/parsers` — Quality Gate

Arquivo: `packages/parsers/src/parsers/quality_gate.py`

```python
from dataclasses import dataclass, field
from .base import ExtractionResult, ExtractionError


@dataclass(frozen=True)
class QualityReport:
    passed: bool
    total_chars: int
    total_pages: int
    total_sheets: int
    empty_pages: int
    rejection_reason: str | None
    warnings: list[str]
```

### Regras — ordem de verificação obrigatória

| Prioridade | Condição | Resultado |
|---|---|---|
| 1 | `result.error` não é None | `passed=False`, `rejection_reason=result.error` |
| 2 | `total_chars < 100` | `passed=False`, `rejection_reason="too_short"` |
| 3 | Todas as páginas têm `is_empty=True` | `passed=False`, `rejection_reason="all_pages_empty"` |
| 4 | `len(chunks) == 0` após chunking | *(ver chunker — falha no worker, não aqui)* |
| 5 | `total_chars > 500_000` | `passed=True` + `warnings += ["content_very_large"]` |
| 6 | Páginas vazias > 30% do total | `passed=True` + `warnings += ["high_empty_page_ratio"]` |
| 7 | `result.warnings` tem itens | Repassar todos para `QualityReport.warnings` |

`empty_pages` deve ser preenchido mesmo quando `passed=True`. Nunca usar LLM.

---

## `packages/parsers` — Chunker

Arquivo: `packages/parsers/src/parsers/chunker.py`

### Tipos obrigatórios

```python
from dataclasses import dataclass
from hashlib import sha256
from datetime import datetime, timezone


@dataclass(frozen=True)
class RawChunk:
    chunk_index: int           # 0-indexed, posição absoluta no documento
    text: str
    char_count: int
    token_estimate: int        # len(text) // 4
    chunk_hash: str            # sha256(text.encode()).hexdigest()
    # proveniência
    source_page: int | None    # PDF/DOCX/TXT
    sheet_name: str | None     # CSV/XLSX
    row_start: int | None      # CSV/XLSX
    row_end: int | None        # CSV/XLSX
    section_heading: str | None
    # metadata estruturado
    metadata: dict             # ver contrato abaixo
```

### Contrato de metadata

`metadata` deve sempre conter:

```python
{
    "parser": "pdf" | "docx" | "csv" | "xlsx" | "txt",
    "source_version": 1,
    "extraction_timestamp": datetime.now(timezone.utc).isoformat(),
}
```

Campos adicionais são permitidos, mas os três acima são obrigatórios.

### Ordem dos chunks

`chunk_index` deve refletir a ordem real de leitura do documento. Chunks devem ser atribuídos na seguinte ordem de precedência:

- PDF/TXT: ordenar por `source_page` crescente, depois posição no texto
- DOCX: ordem de aparição no documento (`page_number=0` para todos, ordenar por posição)
- CSV/XLSX: ordenar por `sheet_name` (ordem das abas), depois por `row_start`

Nunca atribuir `chunk_index` antes de finalizar a lista e ordenar.

### Estratégia PDF / DOCX / TXT

```
1. Para cada página/bloco de texto:
   a. Detectar headings: linha que começa com "#" OU linha ALL CAPS com ≤ 60 chars
   b. Dividir texto em seções por heading
   c. Para cada seção:
      - Se tokens estimados ≤ 800: seção = 1 chunk
      - Se tokens > 800: subdividir em parágrafos (\n\n)
        - Para cada parágrafo:
          - Se tokens ≤ 800: parágrafo = 1 chunk
          - Se tokens > 800: cortar em blocos de 800 com overlap de 100
      - Se bloco < 50 chars: fundir com o próximo bloco
2. Descartar chunks com text.strip() == ""
3. Mínimo de chars por chunk: 50
```

### Estratégia CSV / XLSX

```
1. Para cada ExtractedSheet:
   a. Agrupar linhas em blocos de 15
   b. Cada bloco → 1 chunk
   c. Texto do chunk:
      "Tabela: {sheet_name}\n{header_line}\n{data_lines}"
      onde header_line = "| col1 | col2 | ..." (repetido em todo chunk)
      e data_lines = linhas do bloco em formato pipe
   d. row_start = primeira linha real do bloco
   e. row_end = última linha real do bloco
```

### Falha por zero chunks

Se `chunk_extraction` retornar lista vazia após processar um `ExtractionResult` válido, o worker deve tratar como falha de domínio com `reason="no_chunks_generated"`. O chunker em si não lança exceção — retorna lista vazia e o worker decide.

---

## `workers/ingest` — Logging estruturado

Arquivo: `workers/ingest/src/worker_ingest/logging.py`

```python
import logging
import json
from datetime import datetime, timezone


class StructuredLogger:
    def __init__(self, name: str) -> None:
        self._log = logging.getLogger(name)

    def _emit(self, level: str, event: str, **fields: object) -> None:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **fields,
        }
        getattr(self._log, level)(json.dumps(payload))

    def info(self, event: str, **fields: object) -> None:
        self._emit("info", event, **fields)

    def warning(self, event: str, **fields: object) -> None:
        self._emit("warning", event, **fields)

    def error(self, event: str, **fields: object) -> None:
        self._emit("error", event, **fields)


logger = StructuredLogger("worker_ingest")
```

### Campos proibidos em qualquer log

Nunca logar:
- conteúdo do documento (texto extraído)
- texto de nenhum chunk
- `SUPABASE_SERVICE_ROLE_KEY` ou qualquer secret
- nome de arquivo além do `source_id`
- stack trace completo para erros de domínio (apenas `reason`)

### Eventos obrigatórios

```python
logger.info("ingest_started",   job_id=job_id, source_id=source_id, workspace_id=workspace_id)
logger.info("file_validated",   job_id=job_id, source_id=source_id, file_size_bytes=N)
logger.info("extraction_done",  job_id=job_id, source_id=source_id, total_chars=N, total_pages=N)
logger.info("quality_passed",   job_id=job_id, source_id=source_id, warnings=[...])
logger.info("chunks_stored",    job_id=job_id, source_id=source_id, chunks_created=N)
logger.info("ingest_succeeded", job_id=job_id, source_id=source_id, chunks_created=N)
logger.error("ingest_failed",   job_id=job_id, source_id=source_id, reason=reason, retry=False)
```

---

## `workers/ingest` — Classificação de falhas

Todo erro deve ser classificado antes de decidir sobre retry:

| Tipo de erro | Retry | Exemplos |
|---|---|---|
| `domain_failure` | **não** | `pages_exceeded`, `mime_mismatch`, `too_short`, `no_chunks_generated`, `rows_exceeded` |
| `technical_failure` | **sim** (max 1x) | timeout de DB, conexão Redis, exceção inesperada de IO |

```python
DOMAIN_FAILURES: set[str] = {
    "pages_exceeded",
    "rows_exceeded",
    "mime_mismatch",
    "magic_bytes_fail",
    "too_short",
    "all_pages_empty",
    "no_chunks_generated",
    "empty_file",
    "size_exceeded",
    "extension_blocked",
    "parse_failed",
    "unsupported_format",
}

def is_domain_failure(reason: str) -> bool:
    return reason in DOMAIN_FAILURES
```

Se `is_domain_failure(reason)` → não chamar `self.retry()`, ir direto para `failed`.  
Se não for domain failure → `self.retry(exc=exc)`.

---

## `workers/ingest` — Celery Task

Arquivo: `workers/ingest/src/worker_ingest/tasks.py`

### Assinatura

```python
from celery import Task
from .celery_app import app


@app.task(
    bind=True,
    name="worker_ingest.tasks.ingest_source",
    max_retries=1,
    default_retry_delay=10,
    acks_late=True,
)
def ingest_source(
    self: Task,
    *,
    job_id: str,
    source_id: str,
    workspace_id: str,
    file_path: str,
    declared_mime: str,
    file_hash: str,          # sha256 do arquivo original, calculado pela API no upload
) -> dict:
    ...
```

### Fluxo obrigatório (ordem exata)

```
1. IDEMPOTÊNCIA POR JOB
   job = db.get_job(job_id)
   Se job.status in ("succeeded", "failed"):
       return {"status": job.status, "cached": True}

2. IDEMPOTÊNCIA POR CONTEÚDO
   idempotency_key = sha256(f"{source_id}:{file_hash}".encode()).hexdigest()
   existing = db.get_job_by_idempotency_key(idempotency_key)
   Se existing e existing.id != job_id e existing.status == "succeeded":
       return {"status": "succeeded", "cached": True, "original_job_id": existing.id}

3. INICIAR
   logger.info("ingest_started", ...)
   db.update_job(job_id, status="running", started_at=now())

4. VALIDAR ARQUIVO
   result = validate_file(Path(file_path), declared_mime)
   Se não result.valid:
       → domain_failure → sem retry
       db.update_source(source_id, status="failed")
       db.update_job(job_id, status="failed", error=result.reason, finished_at=now())
       logger.error("ingest_failed", reason=result.reason, retry=False)
       return {"status": "failed", "reason": result.reason}

5. VALIDAR OWNERSHIP
   source = db.get_source(source_id)
   Se source.workspace_id != workspace_id:
       → domain_failure → sem retry
       [mesmo tratamento de falha acima]
       return {"status": "failed", "reason": "workspace_mismatch"}

6. EXTRAIR TEXTO
   parser = get_parser(declared_mime)
   extraction = parser.extract(Path(file_path))
   logger.info("extraction_done", total_chars=extraction.total_chars, ...)
   Se extraction.error:
       is_domain = is_domain_failure(extraction.error)
       [atualizar job e source → failed]
       Se not is_domain: self.retry(...)
       return {"status": "failed", "reason": extraction.error}

7. QUALITY GATE
   report = run_quality_gate(extraction)
   Se não report.passed:
       → domain_failure → sem retry
       [dentro de transação: salvar quality_report + atualizar source + job]
       return {"status": "failed", "reason": report.rejection_reason}

8. CHUNKING
   chunks = chunk_extraction(extraction)
   Se len(chunks) == 0:
       → domain_failure
       return {"status": "failed", "reason": "no_chunks_generated"}

9. PERSISTIR (TRANSAÇÃO ÚNICA)
   with db.transaction():
       db.upsert_quality_report(source_id, report)
       db.delete_chunks_by_source(source_id)    ← idempotência de chunks
       db.insert_chunks(source_id, workspace_id, chunks)
       db.update_source(source_id, status="processing")
       db.update_job(job_id, status="succeeded", finished_at=now(),
                     chunks_created=len(chunks))
   Se transação falhar → rollback automático → self.retry(exc=exc)

10. RETORNAR
    logger.info("ingest_succeeded", chunks_created=len(chunks))
    return {
        "status": "succeeded",
        "chunks_created": len(chunks),
        "total_chars": report.total_chars,
        "warnings": report.warnings,
    }
```

### Idempotência de chunks no banco

Antes de inserir chunks (passo 9), sempre executar:

```sql
DELETE FROM chunks WHERE source_id = :source_id;
```

E garantir a constraint no banco (migration adicional se necessário):

```sql
ALTER TABLE chunks
ADD CONSTRAINT uq_chunk_source_index UNIQUE (source_id, chunk_index);
```

Se a migration 006 já tiver esta constraint, não recriar.

### Concorrência do worker

Em `workers/ingest/src/worker_ingest/celery_app.py`, configurar:

```python
app.conf.update(
    worker_concurrency=2,          # máximo 2 jobs simultâneos por processo
    worker_prefetch_multiplier=1,  # não buscar próxima task antes de terminar a atual
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)
```

---

## Dependências

### `packages/parsers/pyproject.toml`

```toml
[project]
name = "context-builder-parsers"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "pymupdf>=1.24",
  "python-docx>=1.1",
  "openpyxl>=3.1",
]
```

### `packages/security/pyproject.toml`

Adicionar:

```toml
dependencies = [
  "python-magic>=0.4",
]
```

### `workers/ingest/pyproject.toml`

```toml
dependencies = [
  "celery[redis]>=5.3",
  "supabase>=2.4",
  "context-builder-parsers",
  "context-builder-security",
  "context-builder-domain",
]
```

---

## Fixtures de teste

Criar via `packages/parsers/tests/fixtures/create_fixtures.py` (script executável manualmente):

| Arquivo | Conteúdo |
|---|---|
| `good.pdf` | PDF textual, 2 páginas, ~300 chars por página |
| `image_only.pdf` | PDF sem texto selecionável (criar página em branco com PyMuPDF) |
| `good.docx` | DOCX com 2 headings e 3 parágrafos (~200 chars total) |
| `good.csv` | CSV com header + 5 linhas, delimitador `,` |
| `semicolon.csv` | CSV com delimitador `;` |
| `good.xlsx` | XLSX com 2 abas, cada uma com header + 3 linhas |
| `good.txt` | TXT com 3 parágrafos separados por `\n\n` |
| `empty.txt` | Arquivo vazio (0 bytes) |
| `fake.pdf` | Arquivo com extensão `.pdf` mas conteúdo `text/plain` |

---

## Testes obrigatórios

### `test_file_validator.py`

```
✓ good.pdf → valid=True
✓ fake.pdf → valid=False, reason=magic_bytes_fail
✓ empty.txt → valid=False, reason=empty_file
✓ arquivo > 50 MB (mock Path.stat) → valid=False, reason=size_exceeded
✓ arquivo .exe → valid=False, reason=extension_blocked
```

### `test_pdf.py / test_docx.py / test_csv.py / test_xlsx.py / test_txt.py`

```
✓ good.* → total_chars > 0, error=None
✓ page_number / sheet_name preenchidos
✓ sanitize_text aplicado (texto sem bytes inválidos)
✓ arquivo corrompido → error=ExtractionError.PARSE_FAILED (sem exceção não capturada)
✓ PDF com 201 páginas → error=ExtractionError.PAGES_EXCEEDED
✓ CSV com 10001 linhas → error=ExtractionError.ROWS_EXCEEDED
✓ image_only.pdf → pages preenchidas com is_empty=True em todas
```

### `test_quality_gate.py`

```
✓ good extraction → passed=True
✓ total_chars < 100 → passed=False, rejection_reason="too_short"
✓ error presente → passed=False
✓ all_pages is_empty → passed=False, rejection_reason="all_pages_empty"
✓ total_chars > 500k → passed=True, "content_very_large" in warnings
✓ >30% páginas vazias → passed=True, "high_empty_page_ratio" in warnings
```

### `test_chunker.py`

```
✓ 3 parágrafos distintos → ≥ 1 chunk, nenhum vazio
✓ CSV com 30 linhas → 2 chunks (15+15), row_start/row_end corretos
✓ chunk_index é 0-based e contínuo (0, 1, 2, ...)
✓ chunk_hash = sha256(text.encode()).hexdigest()
✓ metadata contém "parser", "source_version", "extraction_timestamp"
✓ extração vazia → lista vazia retornada (sem exceção)
✓ bloco < 50 chars é fundido com o próximo
```

### `test_tasks.py` (worker-ingest, com mocks)

```
✓ job já succeeded → retorna sem reprocessar
✓ mesmo source_id + file_hash já processado → retorna cached
✓ file inválido → source.status = "failed", job.status = "failed"
✓ workspace_mismatch → falha sem retry
✓ zero chunks → falha com "no_chunks_generated"
✓ falha de DB no passo 9 → rollback, self.retry() chamado
✓ domain_failure → self.retry() NÃO é chamado
✓ retorno contém chunks_created, total_chars, warnings
```

---

## O que NÃO fazer

- Não chamar LLM em nenhum ponto desta task.
- Não implementar classificação (TASK-004).
- Não implementar extração estruturada (TASK-005).
- Não implementar endpoints FastAPI (TASK-003).
- Não fazer OCR — página sem texto selecionável → `is_empty=True`.
- Não deduplicar chunks entre sources diferentes.
- Não alterar `supabase/migrations/`.
- Não alterar `docs/`.
- Não expor `SUPABASE_SERVICE_ROLE_KEY` em log.
- Não instanciar parsers diretamente no worker — usar `get_parser()`.
- Não inserir chunks fora de transação.
- Não chamar `self.retry()` em domain failure.

---

## Critérios de aceite

```
[ ] pytest packages/parsers/tests/ -v              → todos passam
[ ] pytest packages/security/tests/ -v             → todos passam
[ ] pytest workers/ingest/tests/ -v                → todos passam
[ ] python -c "from parsers import get_parser, UnsupportedMimeError" → sem erro
[ ] python -c "from parsers.base import ExtractionError"             → sem erro
[ ] python -c "from parsers.quality_gate import QualityReport"       → sem erro
[ ] python -c "from parsers.chunker import RawChunk"                 → sem erro
[ ] python -c "from security.file_validator import validate_file"    → sem erro
[ ] PDF com 2 páginas gera ≥ 1 chunk com source_page preenchido
[ ] XLSX com 2 abas gera chunks com sheet_name distinto
[ ] fake.pdf retorna ValidationResult(valid=False, reason="magic_bytes_fail")
[ ] job já "succeeded" retorna sem reprocessar (teste unitário com mock)
[ ] domain_failure não chama self.retry() (teste unitário com mock)
[ ] retorno do worker contém chunks_created, total_chars, warnings
[ ] celery -A worker_ingest.celery_app worker --dry-run → sem erro
[ ] ruff check .    → zero erros
[ ] mypy packages/parsers packages/security workers/ingest → zero erros
```

---

## Referências

- `CLAUDE.md` — pipeline, regras de retry e limites
- `docs/00-start-here/MVP_DECISIONS.md` — chunking strategy, limites de retry
- `docs/03-pipeline/PIPELINE.md` — contratos de sequência
- `docs/05-security/SECURITY.md` — validação de arquivo e logging
- `supabase/migrations/004_sources.sql` — tabela sources
- `supabase/migrations/005_quality_reports.sql` — tabela source_quality_reports
- `supabase/migrations/006_chunks.sql` — tabela chunks (verificar se constraint UNIQUE existe)
- `supabase/migrations/016_jobs.sql` — tabela processing_jobs
