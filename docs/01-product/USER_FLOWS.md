# USER_FLOWS.md — Fluxos de Usuário

## Fluxo 1 — Upload e ingestão

```
Usuário acessa /user/sources/new
  ↓
Seleciona tipo: Upload Documento
  ↓
Faz drag/drop ou seleciona arquivo
  ↓
Quality gate roda (feedback visual imediato)
  ├── OK → mostra: tipo, legibilidade, estrutura, risco
  │   └── [Iniciar ingestão] → job entra na fila
  └── FAIL → mensagem de rejeição + orientação de como corrigir
```

## Fluxo 2 — Revisão de fatos

```
Usuário acessa /user/review ou notificação de "X fatos pendentes"
  ↓
Vê lista de chunks com estado visual (cor)
  ↓
Seleciona chunk
  ↓
Vê: texto original + extração lado a lado
  ↓
  ├── [Aprovar] → approve_fact/approve_rule → status → approved
  ├── [Editar] → abre modal de edição → approve com conteúdo editado → status → approved
  ├── [Publicar] → publish_fact/publish_rule → status → published → entra em published_facts/published_rules
  ├── [Rejeitar] → status → rejected
  └── [Marcar como Regra] → redireciona para business_rules
```

## Fluxo 3 — Resolução de unknown

```
Usuário acessa /user/unknown
  ↓
Vê chunk com texto + sugestão de label + confiança
  ↓
  ├── [Mapear tipo existente] → dropdown de fact_types → extrai com schema existente
  ├── [Criar novo tipo] → abre formulário → schema vai para admin/schemas como draft
  └── [Ignorar] → status → ignored
```

## Fluxo 4 — Export Context Bundle

```
Usuario acessa /user/context-bundle ou acao equivalente de export
  ->
Sistema calcula readiness:
  - fontes publicadas
  - fatos/regras publicadas
  - unknowns abertos
  - contradicoes abertas
  - evidencia/proveniancia
  ->
Usuario ve status ready/warning/blocked
  ->
Se aprovado, consumidor externo importa context_bundle.v1
```

## Fluxo 4b — Consulta diagnostica interna

Consulta auditavel interna pode existir para QA e diagnostico. Ela nao e o
chatbot final do produto.

```
Usuário acessa /user/query
  ↓
Digita pergunta em linguagem natural
  ↓
Sistema retorna resposta com:
  - texto da resposta
  - confiança
  - status (Validado / Parcial / Conflito)
  - audit_id
  ↓
Usuário pode expandir:
  ├── [Ver fatos usados] → lista de facts publicados com source e versão
  ├── [Ver regras] → regras aplicadas com texto original
  └── [Ver fonte original] → link para o documento/chunk original
```

## Fluxo 5 — Resolução de contradição

```
Notificação: "Conflito detectado em Preço de Limpeza de Pele"
  ↓
Usuário acessa alerta no dashboard
  ↓
Vê: Fonte A (PDF Maio, R$120) vs Fonte B (Planilha Junho, R$150)
  ↓
  ├── [Fonte A prevalece] → Fonte B fact → deprecated
  ├── [Fonte B prevalece] → Fonte A fact → deprecated
  └── [Ambas válidas com contexto] → abre campo de nota obrigatória → resolução manual no registro de contradiction
```

