# MCP_GATEWAY.md — Geração Automatizada de MCP e Gateway de Conectores

> Toda API externa vira conector controlado, não acesso direto.
> Automatizar geração. Manualizar aprovação. Auditar execução.

---

## Princípio arquitetural

```
API externa
  ↓
OpenAPI/Swagger spec
  ↓
MCP bruto gerado automaticamente
  ↓
Classificação de risco por endpoint
  ↓
Allowlist (apenas endpoints aprovados)
  ↓
Normalização de tools
  ↓
Autorização + rate limit
  ↓
Auditoria
  ↓
Agente
  ↓
raw_external_items
  ↓
Pipeline padrão de ingestão (quality gate → chunk → extrair → validar)
```

O MCP não substitui a API. Funciona como interface padronizada e controlada para o agente usar conectores.

---

## Regra central

**Nunca expor uma API inteira diretamente ao agente.**

Todo endpoint é classificado antes de virar tool MCP. No MVP, apenas `read_only` é exposto.

---

## Classificação de endpoints

| Categoria | Exemplos | Exposto no MVP |
|-----------|----------|----------------|
| `read_only` | GET /posts, GET /reviews, GET /hours | ✅ |
| `write_safe` | POST /draft, PUT /description | ❌ V2 |
| `write_dangerous` | POST /publish, POST /send, DELETE | ❌ nunca automático |
| `admin` | POST /users/role, GET /permissions | ❌ nunca |
| `financial` | GET /billing, POST /payment | ❌ nunca |
| `auth_sensitive` | GET /tokens, POST /oauth | ❌ nunca |
| `unsupported` | Endpoints sem spec clara | ❌ |

**Heurísticas de classificação automática:**

```python
def classify_endpoint(method: str, path: str, description: str) -> str:
    path_lower = path.lower()
    desc_lower = description.lower()

    if any(x in path_lower for x in ["token", "auth", "secret", "key", "oauth"]):
        return "auth_sensitive"
    if any(x in path_lower for x in ["billing", "payment", "subscription", "invoice"]):
        return "financial"
    if any(x in path_lower for x in ["admin", "role", "permission", "user"]):
        return "admin"
    if method in ("DELETE", "PUT", "PATCH"):
        return "write_dangerous"
    if method == "POST":
        if any(x in path_lower for x in ["publish", "send", "message", "post"]):
            return "write_dangerous"
        return "write_safe"
    if method == "GET":
        return "read_only"
    return "unsupported"
```

Classificação automática é sugestão — revisão humana obrigatória antes de ativar qualquer tool.

---

## Pipeline de importação de spec

### 5.1 Entrada aceita

- `openapi.json` / `swagger.json`
- URL pública do OpenAPI
- Arquivo YAML
- Documentação manual convertida

### 5.2 Geração do MCP bruto

```python
# Exemplo de tool gerada automaticamente
{
    "tool_name": "get_user_posts",           # gerado automaticamente
    "original_operation_id": "listUserPosts",
    "method": "GET",
    "path": "/users/{id}/posts",
    "input_schema": {
        "user_id": {"type": "string", "required": True},
        "limit": {"type": "integer", "default": 20}
    },
    "risk_category": "read_only",            # classificado automaticamente
    "risk_score": 0.1,
    "status": "pending_review"               # nunca ativo sem revisão
}
```

### 5.3 Normalização de nomes

Tools geradas automaticamente têm nomes ruins. Normalizar antes de expor:

```
GET /v1/business/{id}/reviews
  → auto: get_v1_business_id_reviews
  → normalizado: list_business_reviews
```

Toda tool deve ter: nome claro, descrição curta, `input_schema` explícito, `output_schema` esperado, limites, permissões necessárias, efeitos colaterais.

---

## Modelo de banco

```sql
CREATE TABLE api_specs (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    provider     TEXT NOT NULL,         -- instagram | youtube | google_business | etc.
    spec_url     TEXT,
    spec_hash    TEXT NOT NULL,         -- SHA-256 da spec — detecta mudança
    raw_spec     JSONB,
    version      TEXT,
    status       TEXT DEFAULT 'imported',
    imported_at  TIMESTAMP DEFAULT NOW()
);

CREATE TABLE mcp_tools (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id         UUID NOT NULL,
    api_spec_id          UUID NOT NULL REFERENCES api_specs(id),
    provider             TEXT NOT NULL,
    tool_name            TEXT NOT NULL,
    original_operation_id TEXT,
    method               TEXT NOT NULL,
    path                 TEXT NOT NULL,
    input_schema         JSONB NOT NULL,
    output_schema        JSONB,
    risk_category        TEXT NOT NULL,
    risk_score           NUMERIC,
    status               TEXT DEFAULT 'pending_review',
    -- pending_review | approved | rejected | deprecated
    reviewed_by          UUID,
    reviewed_at          TIMESTAMP,
    created_at           TIMESTAMP DEFAULT NOW()
);

CREATE TABLE mcp_tool_allowlist (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id            UUID NOT NULL,
    tool_id                 UUID NOT NULL REFERENCES mcp_tools(id),
    enabled                 BOOLEAN DEFAULT false,
    requires_human_approval BOOLEAN DEFAULT false,
    max_calls_per_hour      INT DEFAULT 100,
    allowed_roles           TEXT[] DEFAULT ARRAY['manager','owner'],
    created_by              UUID,
    created_at              TIMESTAMP DEFAULT NOW(),
    UNIQUE(workspace_id, tool_id)
);

CREATE TABLE mcp_tool_calls (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id     UUID NOT NULL,
    tool_id          UUID NOT NULL REFERENCES mcp_tools(id),
    user_id          UUID,
    agent_session_id UUID,
    input_hash       TEXT,              -- hash dos parâmetros de entrada
    output_hash      TEXT,              -- hash da resposta (não a resposta em si)
    result_count     INT,               -- número de itens retornados
    status           TEXT NOT NULL,     -- success | error | rate_limited | unauthorized
    latency_ms       INT,
    created_at       TIMESTAMP DEFAULT NOW()
);

CREATE TABLE raw_external_items (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL,
    tool_call_id UUID REFERENCES mcp_tool_calls(id),
    source_type  TEXT NOT NULL,         -- social_post | review | official_api | etc.
    provider     TEXT NOT NULL,
    raw_content  JSONB NOT NULL,
    content_hash TEXT NOT NULL,
    status       TEXT DEFAULT 'pending_ingestion',
    created_at   TIMESTAMP DEFAULT NOW()
);
```

---

## Fluxo OAuth — tokens fora do MCP

```
Agente
  ↓ chama tool MCP (sem token)
MCP Gateway valida: workspace_id, user_id, role, tool habilitada, rate limit
  ↓
Connector busca token no Secret Manager (nunca no payload)
  ↓
API externa é chamada
  ↓
Resposta é filtrada (remover PII desnecessária, truncar se grande)
  ↓
raw_external_items
  ↓
Pipeline de ingestão padrão
```

**O agente nunca recebe:** access token, refresh token, client secret, headers internos, stack trace, resposta bruta sensível.

---

## Auditoria por chamada

```json
{
    "workspace_id": "ws_001",
    "user_id": "usr_001",
    "tool": "list_business_reviews",
    "provider": "google_business",
    "input_hash": "sha256:...",
    "result_count": 20,
    "status": "success",
    "latency_ms": 340,
    "created_at": "2026-05-05T10:00:00Z"
}
```

**Nunca registrar:** token, conteúdo completo da resposta, mensagens privadas, PII desnecessária, segredo.

---

## Política de exposição por versão

| Versão | Permitido |
|--------|-----------|
| MVP | Nada — MCP não existe ainda |
| V1 | `read_only`, sem dados sensíveis, sem paginação infinita |
| V2 | `write_safe` com human approval obrigatório |
| Nunca | delete, billing, admin, token, publish/send automático |

---

## Validação por chamada

Cada chamada MCP valida, nesta ordem:

1. `workspace_id` válido e ativo
2. `user_id` membro do workspace com role suficiente
3. Tool está na allowlist e `enabled = true`
4. Role do usuário está em `allowed_roles`
5. Escopo OAuth cobre o endpoint
6. Rate limit não foi excedido
7. Tamanho da resposta dentro do limite

Qualquer falha: retornar erro com código semântico, nunca informação de debug.

---

## Estrutura de pacotes

```
packages/
  mcp_generator/
    openapi_loader.py        # importa e valida spec
    tool_generator.py        # gera mcp_tools a partir da spec
    risk_classifier.py       # classifica risco por endpoint
    allowlist_builder.py     # gera allowlist inicial para revisão
    schema_normalizer.py     # normaliza nomes e schemas

  mcp_gateway/
    server.py                # servidor MCP
    auth.py                  # validação de workspace, user, role
    audit.py                 # log de chamadas
    rate_limit.py            # controle de uso
    tool_registry.py         # registry das tools ativas

  connectors/
    google_business/
    google_drive/
    google_sheets/
    instagram/
    youtube/
    whatsapp/
```

---

## Human approval para ações de escrita (V2+)

Ações que sempre exigem aprovação humana antes de executar:

- Publicar fato extraído de fonte externa
- Atualizar regra operacional com base em dado externo
- Responder cliente via API
- Publicar post social
- Enviar mensagem
- Deletar dado
- Exportar dados do workspace
- Alterar permissão

---

## Conectores prioritários para V2

Ordenados por valor / risco / facilidade de auditoria:

1. Google Sheets — tabelas de preço, catálogos (baixo risco, alto valor)
2. Google Drive — documentos internos (baixo risco, alto valor)
3. Google Business Profile — horários, endereço, reviews (médio risco, alto valor)
4. YouTube — descrições, FAQs (baixo risco)
5. Instagram/Facebook Graph API — posts, horários, catálogo (médio risco)
6. WhatsApp Business API — catálogo, templates (alto risco, requer cuidado extra)

