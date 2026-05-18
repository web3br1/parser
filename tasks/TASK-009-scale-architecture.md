# TASK-009 - Scale Architecture and Configurability

**Projeto:** Context Builder Empresarial  
**Status:** `ready`  
**Versao:** 1.0  
**Agente:** Claude Code / Codex  
**Estimativa:** 1-2 sessoes  
**Depende de:** TASK-007, TASK-008  
**Bloqueia:** multi-tenant serio, tuning por workspace, troca segura de modelos

---

## Objetivo

Remover constantes hardcoded e acoplamentos entre workers, preparar configuracao por workspace e melhorar a assinatura de prompts/modelos. Esta task deixa o sistema pronto para escalar sem recompilar codigo para cada ajuste operacional.

---

## Problemas que esta task fecha

| Achado | Risco | Status esperado |
|---|---|---|
| Thresholds hardcoded | Recompilar para ajustar sensibilidade | Config por workspace |
| Late import entre workers | Acoplamento e circularidade | `packages/queue_manager` |
| Hash do prompt ignora model/provider | Cache/idempotencia incorreta | prompt signature completa |
| PDF escaneado vira `all_pages_empty` | UX confusa | `ocr_required` separado |
| `joined_at` usa relogio da API | Inconsistencia temporal | DB clock via RPC/default |
| Upload em memoria | OOM sob concorrencia | streaming/spooled file |
| Chunk heading por `isupper()` | Quebra semantica | heuristica revisada |

---

## Arquivos a criar ou modificar

```text
packages/
  queue_manager/
    pyproject.toml
    src/queue_manager/
      __init__.py
      contracts.py
      celery_dispatcher.py
      idempotency.py
    tests/
      test_idempotency.py
      test_dispatcher.py

  workspace_config/
    pyproject.toml
    src/workspace_config/
      __init__.py
      settings.py
      defaults.py
    tests/
      test_settings.py

supabase/migrations/
  033_workspace_pipeline_settings.sql

apps/api/src/context_builder/
  routers/workspaces.py
  routers/sources.py

packages/parsers/src/parsers/
  quality_gate.py
  chunker.py

workers/classification/src/worker_classification/
  classifier.py
  prompt.py
  extraction_queue.py

workers/extraction/src/worker_extraction/
  prompt.py

workers/ingest/src/worker_ingest/
  tasks.py
```

---

## Workspace pipeline settings

Criar tabela:

```sql
create table public.workspace_pipeline_settings (
  workspace_id uuid primary key references public.workspaces(id) on delete cascade,
  classification_confidence_threshold numeric(5,4) not null default 0.75,
  max_chunk_tokens integer not null default 800,
  chunk_overlap_tokens integer not null default 100,
  quality_min_chars integer not null default 100,
  ocr_enabled boolean not null default false,
  model_provider text not null default 'openai',
  classification_model text not null default 'gpt-4o-mini',
  extraction_model text not null default 'gpt-4o',
  query_model text not null default 'gpt-4o',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
```

RLS:

```text
members can view
owners/managers can update
```

---

## Config resolution

Criar pacote `workspace_config` com contrato:

```python
@dataclass(frozen=True)
class PipelineSettings:
    classification_confidence_threshold: float
    max_chunk_tokens: int
    chunk_overlap_tokens: int
    quality_min_chars: int
    ocr_enabled: bool
    model_provider: str
    classification_model: str
    extraction_model: str
    query_model: str


def get_pipeline_settings(workspace_id: str) -> PipelineSettings:
    ...
```

Ordem de resolucao:

```text
1. workspace_pipeline_settings
2. defaults.py
3. environment vars apenas para defaults globais
```

---

## Prompt signature

Substituir `get_prompt_version()` por assinatura de comportamento:

```python
def get_prompt_signature(
    *,
    template: str,
    provider: str,
    model: str,
    schema_version: str,
) -> str:
    payload = {
        "template_hash": sha256(template.encode()).hexdigest(),
        "provider": provider,
        "model": model,
        "schema_version": schema_version,
    }
    return sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
```

Regras:

```text
Trocar prompt -> muda signature
Trocar modelo -> muda signature
Trocar provider -> muda signature
Trocar schema_version -> muda signature
```

Atualizar idempotency keys de classification/extraction para usar `prompt_signature`.

---

## Queue manager

Criar `packages/queue_manager` para remover late imports entre workers.

Contrato:

```python
@dataclass(frozen=True)
class QueueJob:
    job_id: str
    job_type: Literal["ingest", "classification", "extraction"]
    payload: dict[str, object]


class QueueDispatcher(Protocol):
    def dispatch(self, job: QueueJob) -> None:
        ...
```

`worker_classification.extraction_queue` deve depender de `queue_manager`, nao de `worker_extraction.tasks`.

---

## OCR-required quality state

Hoje PDF escaneado vira `all_pages_empty`. Separar:

```text
all_pages_empty -> documento realmente sem conteudo textual e sem paginas uteis
ocr_required -> paginas existem, texto selecionavel vazio, tipo PDF
```

No MVP:

```text
ocr_enabled=false -> rejeitar com reason="ocr_required"
ocr_enabled=true -> enviar para futuro OCR worker (stub), sem implementar OCR nesta task
```

Nao implementar OCR real.

---

## Upload streaming

Trocar leitura total em memoria por `SpooledTemporaryFile`.

Regras:

```text
calcular sha256 incrementalmente
validar limite de 50 MB durante leitura
validar magic bytes no arquivo temporario
upload ao storage lendo do arquivo temporario
cleanup no finally
```

Aceite de memoria:

```text
arquivo de 50 MB nao deve existir simultaneamente como bytes completo + temp file
```

---

## Chunker heading heuristic

Substituir regra simples `line.isupper()` por heuristica mais conservadora:

```text
heading se:
  - linha comeca com "#"
  OU
  - linha ALL CAPS <= 60 chars
    E linha anterior esta vazia
    E linha seguinte nao esta vazia
    E nao termina com pontuacao de frase (.!?)
```

Adicionar testes para:

```text
AVISO IMPORTANTE no meio do paragrafo nao quebra chunk
Heading em caixa alta isolado quebra secao
```

---

## joined_at

Workspace creation deve usar RPC `create_workspace_with_owner` e deixar `joined_at` ser definido pelo banco.

Regra:

```text
API nao envia joined_at manualmente
Banco usa default now() ou RPC usa now()
```

---

## Testes obrigatorios

```text
[ ] workspace sem settings usa defaults
[ ] workspace com threshold customizado altera roteamento classification
[ ] prompt signature muda quando model muda
[ ] prompt signature muda quando provider muda
[ ] prompt signature muda quando schema_version muda
[ ] queue_manager dispatcha extraction sem late import de worker_extraction
[ ] quality gate retorna ocr_required para PDF image-only
[ ] ocr_required nao e confundido com all_pages_empty
[ ] upload streaming calcula mesmo hash que bytes direto
[ ] upload > 50 MB falha durante leitura
[ ] temp file de upload e removido no finally
[ ] chunker nao quebra frase ALL CAPS no meio do paragrafo
[ ] workspace create nao envia joined_at pela API
```

---

## O que NAO fazer

- Nao implementar OCR real.
- Nao implementar UI de settings.
- Nao criar dashboard.
- Nao trocar Celery por outra fila.
- Nao remover compatibilidade com env vars globais.
- Nao alterar fact schemas do MVP.

---

## Criterios de aceite

```text
[ ] Migration 033 cria workspace_pipeline_settings com RLS
[ ] packages/workspace_config existe e e usado por classification/extraction/chunker
[ ] confidence threshold nao esta hardcoded como unica fonte de verdade
[ ] prompt_version foi substituido ou complementado por prompt_signature
[ ] idempotency keys usam prompt_signature
[ ] packages/queue_manager remove late import de worker_extraction em classification
[ ] quality gate diferencia ocr_required de all_pages_empty
[ ] upload usa streaming/spooled temp file
[ ] create_workspace usa DB clock para joined_at
[ ] pytest packages/ workers/ tests/api/ passa
[ ] ruff check . retorna zero erros
[ ] mypy packages/ apps/api workers/ retorna zero erros
```
