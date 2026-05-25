# Production blockers from patch review

Data da revisao: 2026-05-16.

Este documento registra os problemas estruturais encontrados nos patches recentes
e transforma cada achado em correcao verificavel antes de producao.

## Decisao go/no-go

O sistema nao deve ir para producao com dados reais de cliente enquanto houver
qualquer item P1 aberto.

Itens P2 nao sao todos bloqueadores isolados, mas bloqueiam um rollout
responsavel se nao houver mitigacao documentada, escopo restrito e aceite
explicito do risco. Itens P3 nao bloqueiam piloto controlado, mas devem entrar
no plano antes de escala.

Classificacao:

| Prioridade | Significado para producao |
|------------|----------------------------|
| P1 | Bloqueia producao. Pode expor dado incorreto, vazar dado nao publicado, quebrar CI ou deixar contratos centrais inconsistentes. |
| P2 | Bloqueia producao geral sem mitigacao. Pode ser aceito apenas em piloto interno/controlado com risco registrado. |
| P3 | Nao bloqueia piloto controlado, mas bloqueia escala, manutencao ou SLO confiavel. |

## Bloqueadores P1

### 1. Publicacao nao e garantida no banco

Problema: `published_facts` e `published_rules` filtram o status do fato/regra,
mas nao garantem que a `source` tambem esta publicada, ativa e nao deletada.
Parte da API compensa em Python, mas outros servicos podem consultar as views
diretamente.

Impacto: conteudo de source nao publicada, deletada, deprecada ou ainda em
validacao pode aparecer em superficies de conhecimento.

Correcao obrigatoria:

- tornar o contrato de publicacao consistente no banco, preferencialmente
  fazendo as views publicadas juntarem `sources` e exigirem `sources.status =
  'published'`, `deleted_at is null` e demais regras de validade;
- remover filtros corretivos duplicados em Python ou mante-los apenas como
  defesa secundaria;
- adicionar testes que provem que fact/rule publicado em source nao publicada
  nao aparece em knowledge nem query.

Validacao:

```powershell
uv run pytest tests\api\test_query.py tests\api\test_knowledge.py tests\integrity -q
```

Estado verificado em 2026-05-25: resolvido nos gates locais. Evidencia:

```powershell
uv run --cache-dir .uv-cache pytest tests\api\test_query.py tests\api\test_knowledge.py tests\integrity -q
# 72 passed
```

### 2. Contrato de estado da source esta dividido

Problema: a migration adiciona `source_status = 'extracted'`, mas o enum de
dominio nao conhece esse estado. Alem disso, a finalizacao de source ignora
chunks em `needs_review` e unknowns abertos ao decidir entre `published` e
`extracted`.

Impacto: uma source pode parecer publicada ou terminal enquanto ainda ha
pendencias de revisao, e partes do codigo podem nao conseguir representar o
estado real do banco.

Correcao obrigatoria:

- alinhar enum de banco, dominio Python e qualquer tipo TypeScript de source
  status;
- definir uma state machine unica para source;
- considerar fatos, regras, chunks, unknowns e contradicoes no agregador de
  estado;
- adicionar teste de source com unknown aberto e chunk `needs_review`.

Validacao:

```powershell
uv run pytest tests\integrity workers\classification\tests workers\extraction\tests workers\ingest\tests -q
npm run typecheck:python:strict-full
```

Estado verificado em 2026-05-25: resolvido nos gates locais. Evidencia:

```powershell
uv run --cache-dir .uv-cache pytest tests\integrity workers\classification\tests workers\extraction\tests workers\ingest\tests -q
# 109 passed
npm run typecheck:python:strict-full
# Success: no issues found in 105 source files
```

### 3. Query e publicacao discordam sobre contradicoes

Problema: publicacao bloqueia contradicoes com status `open` e `needs_review`,
mas query so trata `open` como contradicao aberta.

Impacto: a API pode retornar uma resposta normal para informacao com conflito
ainda em revisao.

Correcao obrigatoria:

- centralizar a definicao de "contradicao bloqueante";
- aplicar a mesma regra em publish, query e testes;
- cobrir `needs_review` em testes de query.

Validacao:

```powershell
uv run pytest tests\api\test_query.py -q
```

Estado verificado em 2026-05-25: resolvido nos gates locais. Evidencia:

```powershell
uv run --cache-dir .uv-cache pytest tests\api\test_query.py -q
# 31 passed
```

### 4. Query ignora unknown queue para dados pendentes

Problema: `needs_human_validation` considera facts/rules pendentes, mas nao
considera `unknown_facts_queue`.

Impacto: perguntas relacionadas a conteudo desconhecido ou rejeitado para
triagem podem retornar `not_found`, escondendo que ha informacao aguardando
revisao humana.

Correcao obrigatoria:

- incluir unknowns abertos/relevantes na deteccao de dado pendente;
- nunca incluir o conteudo do unknown no contexto de resposta;
- adicionar teste de unknown-only resultando em `needs_human_validation`.

Validacao:

```powershell
uv run pytest tests\api\test_query.py -q
```

Estado verificado em 2026-05-25: resolvido nos gates locais. Evidencia:

```powershell
uv run --cache-dir .uv-cache pytest tests\api\test_query.py -q
# 31 passed
```

### 5. Gate Python de CI esta vermelho

Problema: o workflow roda mypy strict, mas o comando atual falha com erros de
tipo. Testes e lint passam, mas a definicao formal de CI nao esta verde.

Impacto: nao existe criterio reprodutivel de release. Produzir nesse estado
normaliza ignorar um gate que ja esta documentado como obrigatorio.

Correcao obrigatoria:

- corrigir os erros de mypy ou reduzir temporariamente o escopo do gate com
  justificativa documentada;
- impedir que um comando de typecheck "passe" sem validar pacotes reais;
- alinhar `package.json`, CI e docs de regression gates.

Validacao:

```powershell
uv run ruff check .
uv run pytest -q
npm run typecheck:python
npm run typecheck:python:strict-full
corepack pnpm --filter @context-builder/web typecheck
corepack pnpm --filter @context-builder/web build
```

Estado aplicado em 2026-05-16: o gate obrigatorio valida pacotes reais com
`npm run typecheck:python` e tambem cobre API/workers com
`npm run typecheck:python:strict-full`. Ambos passam e devem permanecer como
gates de release.

Estado verificado em 2026-05-25:

```powershell
npm run typecheck:python
# Success: no issues found in 36 source files
npm run typecheck:python:strict-full
# Success: no issues found in 105 source files
```

## Riscos P2 que exigem mitigacao antes de producao geral

### 6. Lifecycle de retries do ingest e inconsistente

Correcao: alinhar ingest com classification/extraction para marcar retrying,
failed terminal e source final state em falhas tecnicas apos retry exhaustion.

Validacao: testes de falha tecnica em ingest cobrindo estado do job e da source.

### 7. Idempotencia de classification pode deixar jobs orfaos

Correcao: usar uma unica chave de idempotencia entre enqueue e worker, ou fazer
o worker marcar o job atual como succeeded/skipped quando retornar cached.

Validacao: teste com job antigo succeeded e novo job queued para o mesmo chunk.

### 8. RLS permite leitura ampla de dados nao revisados

Correcao: decidir se o frontend pode usar Supabase direto. Se sim, restringir
policies por role e separar dados publicados de dados de revisao. Se nao,
documentar API-only e adicionar guardrails para nao introduzir cliente Supabase
com chave de usuario sem revisar as policies.

Validacao: testes/smokes negativos por role para chunks, facts nao publicados,
unknowns e contradictions.

### 9. API depende de pacote de worker

Correcao: remover import direto de task Celery no API, substituindo por uma
porta fina de enfileiramento ou pacote compartilhado sem dependencias de worker.

Validacao: API sobe e roda testes sem instalar dependencias pesadas de parsing
ou worker quando possivel.

### 10. Privacidade registra pedidos, mas nao executa export/delete

Correcao: deixar a API honesta sobre o estado atual ou implementar worker de
export/delete com dry-run, confirmacao, auditoria e relatorio final.

Validacao: testes para request, dry-run, confirmacao, execucao e auditoria.

### 11. Anthropic gateway esta declarado, mas nao implementado

Problema: `packages/model_gateway/src/model_gateway/anthropic_client.py` ainda
lança `NotImplementedError` em `classify` e `extract`.

Mitigacao atual: o piloto usa Ollama como provider padrao. Nao configurar
`MODEL_PROVIDER=anthropic` em piloto/release enquanto o gateway nao for
implementado e coberto por testes.

Correcao: implementar o gateway Anthropic ou remover/desabilitar a opcao
explicitamente da selecao de providers suportados.

Validacao: testes de `model_gateway` cobrindo classify/extract Anthropic com
cliente mockado e fallback seguro de erro.

## Riscos P3 antes de escala

### 12. Listagens paginam em memoria e review faz N+1

Correcao: mover paginacao/ordenacao para o banco e carregar contadores/agregados
em queries batched.

Validacao: testes de paginacao deterministica e smoke com volume sintetico.

## Ordem recomendada de correcao

1. Corrigir published views e knowledge/query para exigir source publicada.
2. Unificar source state machine e enum `extracted`.
3. Unificar regra de contradicao bloqueante.
4. Incluir unknown queue em `needs_human_validation`.
5. Fazer CI/typecheck refletir gates reais.
6. Corrigir lifecycle e idempotencia dos workers.
7. Decidir e endurecer RLS para acesso direto ou API-only.
8. Separar API de worker runtime.
9. Tornar fluxos LGPD executaveis ou claramente request-only.
10. Implementar ou desabilitar explicitamente o gateway Anthropic.
11. Otimizar paginacao e N+1 antes de escala.

## Criterio minimo para liberar producao

Antes de producao com dados reais:

- nenhum P1 aberto;
- P2 com correcao pronta ou mitigacao assinada no release note;
- todos os comandos de validacao passam;
- smoke Supabase real passa;
- `docs/07-qa/ACCEPTANCE_CRITERIA.md` esta atualizado com o estado real;
- release note lista explicitamente qualquer risco residual aceito.
