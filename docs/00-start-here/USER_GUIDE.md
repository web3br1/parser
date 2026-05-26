# USER_GUIDE.md - Guia completo de uso do Parser

Este guia explica como usar o Parser como Context Compiler local. O objetivo do
app e transformar documentos fonte em conhecimento validado, auditavel e
exportavel como `context_bundle.v1` para outro projeto consumir.

O Parser nao e o chatbot final. Ele e o upstream parser/context builder: recebe
documentos, valida qualidade, extrai facts/rules/evidence/gaps/tests, permite
revisao humana, publica conhecimento aprovado e exporta um bundle seguro.

## 1. Quem usa o app

| Perfil | O que faz |
|---|---|
| Operador | Sobe fontes, acompanha jobs, revisa itens e publica conhecimento |
| Manager/owner | Pode fazer upload, revisar, publicar, exportar bundle e solicitar privacidade |
| Reviewer | Revisa itens quando permitido, mas nao publica em producao |
| Desenvolvedor | Roda API/workers/console, migrations, testes e smokes |
| Runtime externo | Importa `context_bundle.v1`; nao conversa diretamente com o Parser |

## 2. Fluxo mental correto

```text
documentos fonte
  -> preflight / quality gate
  -> ingest / parsing / chunks
  -> classificacao
  -> extracao estruturada
  -> facts, rules, evidence, gaps, tests
  -> revisao humana
  -> publicacao
  -> context_bundle.v1
  -> runtime/chatbot externo
```

Para source packs normalizados, o fluxo encurta:

```text
pasta ou zip com 00_source_manifest.md
  -> source-pack preflight
  -> import run auditavel
  -> source-pack compiler
  -> context_bundle.v1
```

## 3. Pre-requisitos locais

Ferramentas esperadas:

- Python 3.12
- `uv`
- Node/Corepack/pnpm
- Docker, se for usar runtime local reproduzivel
- Supabase CLI, se for aplicar migrations reais
- Redis, Docker Redis ou outro broker compativel com `REDIS_URL`

Arquivo local:

```text
.env
```

Crie a partir de `.env.example` quando existir. Nunca coloque secrets em docs,
commits, logs compartilhados ou bundles.

Variaveis mais importantes:

```dotenv
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
WORKSPACE_STORAGE_BUCKET=context-builder-private
REDIS_URL=redis://localhost:6379/0
API_BASE_URL=http://localhost:8000
APP_ENV=development
LOG_LEVEL=INFO

MODEL_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
CLASSIFICATION_MODEL=
EXTRACTION_MODEL=
EXTRACTION_MODEL_FALLBACK=
```

Use `MODEL_PROVIDER=ollama` para piloto local. Chaves externas como
`OPENAI_API_KEY` e `ANTHROPIC_API_KEY` ficam vazias a menos que uma rodada de
fallback seja explicitamente aprovada.

## 4. Instalar dependencias

Na raiz do repo:

```powershell
uv sync
corepack pnpm install
```

Verifique a base:

```powershell
uv run --cache-dir .uv-cache pytest -q
uv run --cache-dir .uv-cache ruff check .
npm run typecheck:python
npm run typecheck:python:strict-full
```

## 5. Subir o runtime local

O caminho preferencial para piloto/desenvolvimento integrado e Docker:

```powershell
docker compose up --build
```

Health check:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

Resultado esperado:

```json
{"status":"ok"}
```

Servicos esperados:

| Servico | Funcao |
|---|---|
| API FastAPI | Recebe uploads, consultas, revisao e export |
| Redis | Broker de workers |
| worker-ingest | Parsing, quality gate e chunks |
| worker-classification | Classificacao por chunk |
| worker-extraction | Extracao estruturada |
| web console | Interface interna de operador |

O smoke real valida uma stack ja em execucao; ele nao deve iniciar/parar
servicos por conta propria.

## 6. Usar o console web

Suba o frontend:

```powershell
corepack pnpm --filter @context-builder/web dev --hostname 127.0.0.1 --port 3000
```

Abra:

```text
http://127.0.0.1:3000/login
```

Cole um JWT de operador. Nunca cole service-role key no browser.

Rotas principais:

| Rota | Uso |
|---|---|
| `/workspaces` | Listar/criar workspaces |
| `/workspaces/{workspaceId}` | Dashboard operacional |
| `/workspaces/{workspaceId}/context-build` | Wizard unico para documento, lote ou source pack |
| `/workspaces/{workspaceId}/sources` | Upload e lista de fontes |
| `/workspaces/{workspaceId}/sources/{sourceId}` | Detalhes da fonte e job |
| `/workspaces/{workspaceId}/review` | Revisar facts/rules extraidos |
| `/workspaces/{workspaceId}/unknown` | Resolver desconhecidos |
| `/workspaces/{workspaceId}/query` | Consulta auditavel contra conhecimento publicado |
| `/workspaces/{workspaceId}/knowledge` | Navegacao de conhecimento publicado quando endpoint existir |
| `/workspaces/{workspaceId}/settings` | Privacidade/export/delete request |

Antes de demo:

```powershell
corepack pnpm --filter @context-builder/web typecheck
corepack pnpm --filter @context-builder/web build
node scripts\smoke\frontend_console_smoke.mjs --base-url http://127.0.0.1:3000
```

## 7. Fluxo de uso por upload normal

Use este fluxo quando o usuario joga arquivos soltos: PDF textual, DOCX, XLSX,
CSV, TXT ou texto equivalente.

1. Entrar no console.
2. Selecionar workspace.
3. Ir em `Sources`.
4. Enviar arquivo.
5. Acompanhar o job da fonte.
6. Esperar ingest/classification/extraction.
7. Ir em `Review`.
8. Aprovar, editar, rejeitar ou publicar facts/rules.
9. Ir em `Unknown`.
10. Reclassificar ou ignorar itens desconhecidos.
11. Exportar ou consultar apenas conhecimento publicado.

Contrato API do upload:

```http
POST /workspaces/{workspace_id}/sources/upload
```

Resultado esperado:

```json
{
  "source_id": "...",
  "job_id": "...",
  "status": "queued",
  "message": "File accepted. Processing started."
}
```

Regras importantes:

- somente `owner` e `manager` fazem upload;
- arquivos duplicados retornam conflito em vez de reprocessar;
- MIME falso, arquivo grande, macro suspeita e zip bomb devem ser rejeitados;
- dados nao publicados nao entram no bundle.

## 8. Fluxo de uso por source pack

Use este fluxo quando o usuario envia uma pasta/zip normalizada com
`00_source_manifest.md`.

Exemplo canonico:

```powershell
C:\tmp\context-builder-sources\compounding-pharmacy-gold
```

### 8.1 Preflight

O preflight identifica se a pasta e:

| Resultado | Significado |
|---|---|
| `compile_as_source_pack` | Manifesto completo; pode compilar como pacote |
| `normal_ingest` | Nao e source pack; tratar como upload normal |
| `reject` | Manifesto existe, mas esta incompleto/invalido |

Endpoint:

```http
POST /workspaces/{workspace_id}/sources/source-pack/preflight
```

Request simples:

```json
{
  "source_dir": "C:\\tmp\\context-builder-sources\\compounding-pharmacy-gold"
}
```

Request com persistencia auditavel:

```json
{
  "source_dir": "C:\\tmp\\context-builder-sources\\compounding-pharmacy-gold",
  "persist": true
}
```

Quando `persist=true`, a resposta inclui:

```json
{
  "import_run_id": "..."
}
```

O import run registra workspace, actor, source pack id/version, contagens,
arquivos faltantes/extras, `input_hash`, status e acao recomendada.

### 8.2 Compilar source pack pelo CLI

Gerar bundle no caminho default:

```powershell
uv run --cache-dir .uv-cache python scripts\source_pack\compile_context_bundle.py C:\tmp\context-builder-sources\compounding-pharmacy-gold
```

Gerar bundle em caminho explicito:

```powershell
uv run --cache-dir .uv-cache python scripts\source_pack\compile_context_bundle.py --source-dir C:\tmp\context-builder-sources\compounding-pharmacy-gold --output C:\tmp\context-builder-sources\compounding-pharmacy-gold\compounding-pharmacy-gold.context_bundle.v1.json
```

Checar se o arquivo existente esta atualizado:

```powershell
uv run --cache-dir .uv-cache python scripts\source_pack\compile_context_bundle.py --source-dir C:\tmp\context-builder-sources\compounding-pharmacy-gold --check
```

Saida esperada:

```text
context_bundle.v1 sha256:... sources=... output=...
```

## 9. Exportar Context Bundle pelo banco/API

Depois que fontes, facts e rules foram revisados e publicados, o consumidor
externo pode buscar:

```http
GET /workspaces/{workspace_id}/context-bundle
```

O resultado e um `ContextBundleResponse` com:

- `schema_version`
- `context_version`
- `workspace_id`
- `generated_at`
- `identity`
- `sources`
- `facts`
- `rules`
- `evidence`
- `gaps`
- `tests`
- `memory_policy`
- `tool_recommendations`
- `readiness`
- `integrity.bundle_hash`

O export bem-sucedido deve gerar audit log com acao `context_bundle.export`.

## 10. Como interpretar readiness

| Status | O que fazer |
|---|---|
| `ready` | Pode importar no runtime externo |
| `warning` | Pode importar, mas deve exibir ou registrar avisos |
| `blocked` | Nao ativar como contexto de producao |

Exemplos de warning:

- estoque sintetico;
- precos sinteticos;
- ERP nao integrado;
- DCB oficial completa ainda nao materializada.

Exemplos de bloqueio:

- secrets no pacote;
- raw prompts;
- stack traces;
- paths privados no bundle;
- source sem status publicado;
- regra critica sem evidencia;
- teste critico sem evidence id;
- unknown ou contradicao aberta relevante.

## 11. O que o usuario final deveria fazer

Na UX final, o usuario nao deve rodar CLI nem saber o que e manifesto. O fluxo
esperado e:

1. Arrastar uma pasta ou zip para upload.
2. O app roda preflight.
3. Se houver `00_source_manifest.md`, o app detecta source pack.
4. Se estiver completo, compila como pacote.
5. Se estiver incompleto, mostra arquivos faltantes.
6. Se nao for source pack, segue ingest normal por arquivo.
7. O operador revisa/publica.
8. O runtime externo importa o `context_bundle.v1`.

Hoje, o console ja tem o `Context Build` Wizard para selecionar arquivo(s),
detectar entrada, chamar preflight autoritativo do backend e acompanhar o estado
do build. Quando o browser envia apenas metadados de uma pasta source pack, o
backend identifica o manifesto, mas bloqueia a compilacao ate o conteudo estar
staged no servidor. O compile completo ja funciona para source packs acessiveis
por `source_dir` interno no backend, desde que o caminho esteja dentro de
`CONTEXT_BUILD_ALLOWED_SOURCE_ROOTS` ou da raiz local padrao
`C:\tmp\context-builder-sources`.

## 12. Consultar conhecimento publicado

Consulta interna auditavel:

```http
POST /workspaces/{workspace_id}/query
```

Use essa rota apenas para verificar conhecimento publicado. Ela nao e o chatbot
final e nao deve inventar resposta fora de facts/rules publicados.

Navegacao de conhecimento:

```http
GET /workspaces/{workspace_id}/knowledge
```

## 13. Revisao humana e publicacao

No console:

1. Abra `Review`.
2. Leia o trecho original/evidence.
3. Aprove, edite ou rejeite cada fact/rule.
4. Publique somente quando a fonte estiver correta.
5. Use `Unknown` para casos sem schema ou baixa confianca.

Regra central: sem validacao humana, o dado nao vira verdade operacional.

## 14. Smokes e gates de confianca

Gates locais:

```powershell
uv run --cache-dir .uv-cache pytest -q
uv run --cache-dir .uv-cache ruff check .
npm run typecheck:python
npm run typecheck:python:strict-full
uv run --cache-dir .uv-cache python scripts\ci\secret_scan.py
```

Smoke minimo real:

```powershell
uv run --cache-dir .uv-cache python scripts\smoke\run_real_smoke.py --target local --json-report .run\smoke-local-minimal.json
```

Smoke completo real:

```powershell
uv run --cache-dir .uv-cache python scripts\smoke\run_real_smoke.py --target local --full --json-report .run\smoke-local-full.json
```

Valide primeiro o smoke minimo. So rode o completo depois dele passar.

## 15. Troubleshooting rapido

| Sintoma | Causa provavel | Acao |
|---|---|---|
| `/health` nao responde | API fora do ar | Verificar Docker/API logs |
| upload retorna 403 | role sem permissao | Usar owner/manager |
| upload retorna 409 | arquivo duplicado | Abrir source existente |
| source pack retorna `normal_ingest` | sem `00_source_manifest.md` | Enviar pacote correto ou tratar como arquivos soltos |
| source pack retorna `reject` | manifesto incompleto | Conferir `missing_files` e `extra_files` |
| source pack retorna `source_pack_staging_required` | browser enviou metadados, nao conteudo staged | Usar `source_dir` backend ou aguardar slice de staging folder/zip |
| source pack retorna `source_dir_not_allowed` | caminho interno fora da raiz permitida | Configurar `CONTEXT_BUILD_ALLOWED_SOURCE_ROOTS` ou mover o pacote para raiz permitida |
| bundle `blocked` | lacuna critica/segredo/unknown/contradicao | Corrigir fonte, revisar e recompilar |
| `--check` falha | bundle gerado esta desatualizado | Regerar sem `--check` |
| console nao carrega | JWT ausente/invalido | Login com token de operador |

## 16. Limites atuais conhecidos

- O console detecta pasta/source pack por metadados, mas ainda nao faz staging
  de pasta/zip para compilacao direta no servidor.
- O compilador de source pack ja gera bundle pelo CLI.
- O preflight canonico de context build existe na API.
- Context build runs ja sao persistiveis com `persist=true`.
- O tutor IA existe como sidecar deterministico com tools allowlistadas; sem
  confirmacao explicita ele nao executa mutacao.
- A importacao do bundle pelo chatbot/runtime externo vive fora deste repo.
- Produzir resposta conversacional final nao e responsabilidade do Parser.

## 17. Checklist operacional

Antes de entregar um bundle para o runtime externo:

- [ ] source pack ou fontes passaram preflight/quality gate;
- [ ] sources relevantes estao publicadas;
- [ ] facts/rules relevantes foram revisados;
- [ ] evidence existe para facts/rules criticos;
- [ ] unknowns e contradicoes relevantes foram resolvidos;
- [ ] bundle nao contem secrets, raw prompts, stack traces ou paths privados;
- [ ] readiness e `ready` ou `warning` aceito;
- [ ] `integrity.bundle_hash` foi registrado;
- [ ] runtime externo importou o bundle sem edicao manual.
