# Read-Path Spec — Antigravity Knowledge Layer

> Versão 1.0 — pipeline de retrieval `C1 → C6` com loop adaptativo bounded.
> Escopo: **plano de query (read-path)**. Ingestão (Plano A) e stores (Plano B) são referenciados como contexto, não detalhados.
> Princípio de fundo: *menor viable* — plano mínimo primeiro, escala só sob insuficiência.

---

## 0. Visão Geral

O sistema tem três planos. Este documento especifica o **Plano C**.

```text
PLANO A — Ingestão (write-path, offline)   1..9, termina em A9 Publicação
PLANO B — Stores (escritos por A9)          B1 SQL | B2 Text Index | B3 Graph
PLANO C — Query (read-path, online)         C1..C6  ← este documento
```

**Fronteira inviolável:** o read-path só lê o que passou por A9 Publicação. Nada não-publicado entra em qualquer resposta.

Stores (stack alvo):

```text
B1  Structured Store   SQL — published facts/rules relacionais
B2  Text Index         Chroma (vetorial) + índice lexical (BM25); metadados: section_path, source_authority, version
B3  Graph Store        Kuzu — entities, correlations, communities, claims, section links
```

Fluxo end-to-end:

```text
pergunta
 └─ C1.1 Classifier ──(single-strategy)──────────────┐
 └─ C1.2 Decomposer ──(multi-hop/híbrido)─> Plan DAG ─┤
                                                      ▼
                                              C1.3 Executor
                                       { C2a SQL | C2b Sem | C2c Graph }   (topológico)
                                              │  caminhos textual/grafo
                                              ▼
                                         C3 ChunkRetriever   (rank + cite)
                                              ▼
                                         C4 Assembly   (budget global, resolve versão)
                                              ▼
                                         C5 Sufficiency Gate
                              ┌───────────────┴───────────────┐
                       insufficient + diagnóstico        sufficient
                              ▼                                ▼
                       C1.4 Replanner                      C6 Resposta (com citação)
                              │                            abstain_required
                   ┌──────────┴──────────┐                     ▼
              sobe degrau            budget esgotou        abstain / rota humana
              re-executa             -> abstain/humano
```

---

## 1. Invariantes Globais

```text
published_only         nunca relaxado, nem na degradação do replan
abstain > hallucinate  "sem base publicada suficiente p/ citar" é resultado VÁLIDO, não falha
minimal-first          começa no plano mais barato suficiente; custo: SQL < Semantic < Graph
conflito -> humano     conflito/ambiguidade de versão em doc controlado não é replanejável
determinismo           mesma (query, scope, corpus_version) -> mesmo resultado; LLM-steps cacheados por hash
```

---

## 2. `policy` — Fonte Única De Thresholds E Weights

Lido por C3 (scoring), C1.4 (replan) e C5 (sufficiency). Configurável **por corpus** (quality-mgmt é estrito; outros podem afrouxar).

```yaml
policy:
  corpus_id: <string>

  # C3 — fusão de score
  score_weights:
    base_fusion: rrf            # rrf | minmax_weighted
    authority_boost: <float>
    recency_boost: <float>
    evidence_boost: <float>
    conflict_penalty: <float>
    obsolete_penalty: <float>
    duplicate_penalty: <float>

  # C5 — thresholds de suficiência
  thresholds:
    min_strong_score: <float>       # define "item forte" (sobre score NORMALIZADO do C3)
    min_coverage_ratio: <float>     # fração de subqueries required cobertas
    min_citation_coverage: <float>  # fração de claims factuais com quote
    confidence_floor: <float>       # piso do verdict=sufficient (degrau 4 da ladder baixa este valor)

  # versão
  version_policy: latest_preferred  # latest_only | latest_preferred | as_of(date) | all_versions

  # C1.4 — replan
  replan_budget: 2
```

`version_policy` governa duas coisas: o sinal do `recency_boost` em C3 e a regra discard-vs-penalize de fonte obsoleta. `as_of(date)` é obrigatório para conformidade retroativa ("o que o SOP dizia na data do incidente?").

---

## 3. C1 — Planner

**Responsabilidade:** transformar pergunta → plano executável → resultado suficiente OU abstenção honesta. Nunca: loop infinito; resposta sem base publicada.

### 3.1 Classifier

```text
Nível 1 — regras determinísticas (cobre a maioria SMB, custo ~0):
  sinal estrutural             -> SQL       "quantos / qual a versão / data / status"
  entidade + relação           -> GRAPH     "quais X exigem Y / quem aprova / depende de / conflita"
  explicação textual de 1 alvo -> SEMANTIC  "explique / como funciona / o que diz sobre"

Nível 2 — LLM classifier (só no ambíguo / multi-sinal):
  -> intent + estratégias[] + needs_decomposition

Cache: classificação por (query_normalizada, corpus_version)
Caso trivial: single-strategy PULA o Decomposer (1 step).
```

### 3.2 Decomposer — Plan DAG

O trabalho real é o **binding**: a saída de um step alimenta o scope/candidates do próximo.

```text
Plan { steps: PlanStep[] }

PlanStep {
  id
  strategy:    SQL | SEMANTIC | GRAPH
  query:       subquery
  required:    bool            # C5 só falha coverage em step required
  scope:       campos BINDADOS da saída de steps anteriores
  budget:      sub-budget (fração do budget global do C4)
  depends_on:  step_ids[]
}
```

Exemplo de binding:

```text
Q: "Quem aprova CAPA crítica e em qual documento isso aparece?"

s1  GRAPH     "aprovador de CAPA crítica"         required=true
              -> entity(aprovador) + section_refs[]
s2  SEMANTIC  "regra de aprovação de CAPA"        required=true
              scope.section_refs <- s1.section_refs
              -> C3 -> chunks citáveis
depends: s2 -> s1

C4 une: s1 (o fato: quem) + s2 (texto + citação: onde aparece)
```

s1 (graph) **nunca** busca texto — produz `section_refs`; s2+C3 buscam o citável.

### 3.3 Executor

Roda o DAG em ordem topológica; paraleliza steps sem dependência; aloca sub-budget por step.

### 3.4 Replanner

Consome o diagnóstico do C5. A escala é uma **ladder monotônica**: cada degrau usado no máximo uma vez, sempre subindo, garantindo terminação.

```text
ESCALATION LADDER
  0  plano mínimo inicial
  1  + estratégia / re-decompor    (semantic-only -> + graph hop)
  2  widen scope                   (relaxa section_path / source_authority — NUNCA published_only)
  3  + budget                      (max_chunks / max_tokens ↑)
  4  lower gate bar                (baixa confidence_floor; resposta marcada low-confidence)
  5  abstain / rota humana

DIAGNÓSTICO (do C5) -> ponto de entrada:
  missing_coverage           -> 1, depois 2
  low_retrieval_groundedness -> 3, depois 4
  low_citation_coverage      -> pede C3 com citation_mode=evidence_first
  entity_not_found           -> re-decompor (1); se persiste -> abstain

replan_budget (policy, default 2). Cada replan consome 1 e sobe ≥1 degrau.
Verdicts abstain_required NÃO entram aqui — vão direto pro C6/humano.
```

---

## 4. C3 — ChunkRetriever

**Responsabilidade única:** transformar candidatos (de semantic ou graph) em chunks **citáveis, ranqueados, deduplicados e dentro de budget local**. Dependência zero do graph store.

```text
ChunkRetriever.retrieve(candidates, query, scope, budget, options) -> RankedChunk[]
```

### 4.1 Entrada

```text
candidates:   chunk_ids[] | section_refs[] | evidence_refs[]
              # NÃO aceita entity_refs/correlation_refs — resolução de grafo é trabalho do C2c,
              # que entrega só refs textuais. matched_via='graph' preserva proveniência.
query:        pergunta original ou subquery planejada
scope:        workspace_id, source_ids?, section_path?, entity_ids?, relation_types?,
              version_policy?, source_authority?, published_only=true
budget:       max_chunks, max_tokens, max_sections, min_score?
options:      expand_to_section, include_neighbors,
              dedup_by: content_hash | section_path | source_section,
              citation_mode: evidence_first | chunk_span
```

### 4.2 Saída

```text
RankedChunk {
  chunk_id, source_id, section_path, section_title, page_start, page_end,
  content, score, score_parts, spans[], citations[], matched_via
}

Span {
  evidence_span_id?   # se veio de evidência revisada
  quote, char_start?, char_end?, page_number?, row_number?,
  match_reason        # 'evidence' (publicada) | 'chunk_span' (derivada de busca)
}
```

### 4.3 Scoring — Fundir Antes De Boostar

Não somar escalas cruas (BM25 ilimitado domina cosseno 0–1).

```text
1. base_score = RRF(semantic, lexical)        # ou minmax normalizado por result set
2. score = base_score * boosts/penalties (weights de policy.score_weights)
3. score_parts guarda raw + contribuição normalizada (C4/C5 precisam explicar inclusão)

min_score só sobre score normalizado/final.
```

### 4.4 Ordem Das Operações

```text
resolve refs -> expand (section/neighbors) -> score -> dedup -> budget-truncate

- expand ANTES de dedup        (duas expansões pra mesma seção reintroduzem dup)
- budget DEPOIS de expand      (seção grande estoura tokens; fallback chunk-only se não couber)
- precedência: max_tokens = teto DURO; max_chunks/max_sections = hints
- dedup_by content_hash = duplicata exata; duplicate_penalty (score) = quase-duplicata
```

### 4.5 Regras Invioláveis

```text
published_only=true
sem chunk_id/section_path recuperável     -> descarta
sem source publicada                       -> descarta
source obsoleta                            -> descarta ou penaliza (conforme version_policy)
citação sem quote                          -> não entra em C6
```

---

## 5. C5 — Sufficiency Gate

**Responsabilidade:** decidir se o contexto montado em C4 é suficiente para responder com segurança. C5 **não** responde, **não** busca mais dados, **não** reordena o plano. Emite verdict + diagnóstico acionável.

```text
SufficiencyGate.evaluate(query, plan, assembled_context, budget_state, policy) -> SufficiencyResult
```

### 5.1 Entrada / Saída

```text
assembled_context {
  sql_items[], ranked_chunks[], graph_paths[], citations[],
  conflicts[], source_versions[], coverage_by_subquery[], token_usage
}

SufficiencyResult {
  verdict: sufficient | insufficient | abstain_required
  confidence                 # score agregado dos eixos soft
  reasons[]
  missing[]                  # subqueries required descobertas
  conflict_report?
  suggested_replan_action?
  retrieval_groundedness     # NÃO answer faithfulness — ver 5.4
  citation_coverage
  evidence_coverage
}
```

### 5.2 Two-tier — Determinístico Primeiro

```text
Tier 1 — regras duras, determinísticas (rodam sempre, podem curto-circuitar pra abstain):
  published_context_absent | citação ausente p/ claim factual | conflito | version_ambiguous
  -> verdict SEM LLM, reprodutível, logado

Tier 2 — juízo soft (só se Tier 1 passa):
  coverage strength (sobre steps required) | retrieval_groundedness
  pode usar LLM-judge, MAS cacheia por (query, candidate_set_hash, corpus_version)

confidence = agregado Tier 2; verdict = threshold(confidence, policy.confidence_floor) + Tier 1
```

### 5.3 Reason → Verdict

```text
FORÇA abstain_required (não loopa):      PERMITE insufficient (-> ladder C1.4):
  published_context_absent                 missing_coverage
  conflict_unresolved                      low_retrieval_groundedness
  version_ambiguous                        low_citation_coverage
  budget_exhausted                         entity_not_found
```

### 5.4 Eixos Avaliados

```text
coverage:      cada subquery REQUIRED tem ≥1 item forte (score > min_strong_score)?
groundedness:  há material publicado que SUSTENTARIA a resposta a cada claim?
               (retrieval-sufficiency, pré-geração — NÃO faithfulness do texto final)
citation:      há quote/evidence suficiente para citar (>= min_citation_coverage)?
safety/version: existe conflito, fonte obsoleta ou ambiguidade de versão?
```

`answer_faithfulness` (a resposta gerada de fato traça para o contexto) é um gate **pós-C6** opcional (C5b), fora do MVP. Adicionar quando a auditoria exigir.

### 5.5 Gate ICLR

```text
I  Is the answer inferable from published context?
C  Are citations complete enough?
L  Are lifecycle/version constraints respected?
R  Is retrieval coverage sufficient for the query?

Qualquer item crítico falha -> não gera resposta factual.
```

---

## 6. Contratos De Dados Referenciados

Componentes não detalhados neste ciclo, contrato mínimo para fechar o end-to-end:

```text
C2a SQL Retrieval      query exata contra B1 -> sql_items[]
C2b Semantic Retrieval B2 (híbrido) -> candidate set textual -> C3
C2c Graph Retrieval    B3 traversal -> resolve entity/correlation -> { chunk_ids|section_refs|evidence_refs } -> C3
C4  Context Assembly   dono do budget GLOBAL; aloca entre SQL/RAG/Graph; resolve conflito/versão; monta contexto
C6  Resposta           geração com evidência/citação; respeita low-confidence flag do C5
```

---

## 7. Resumo Do Loop

```text
C1 planeja (mínimo) -> C2 recupera candidatos -> C3 transforma em chunks citáveis
-> C4 monta contexto + budget -> C5 julga suficiência
-> sufficient: C6 responde com citação
-> insufficient: C1.4 sobe a ladder e re-executa (até replan_budget)
-> abstain_required: abstém ou rota humana (não loopa)
```
