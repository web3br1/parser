# Read-Path Quality Improvements

## Scope

This implementation adds the first TypeScript contracts for the Antigravity read-path quality layer under `packages/knowledge-layer`.

- C1.0 `QueryTransformer` rewrites and normalizes subqueries deterministically.
- Vocabulary grounding is based on published graph terms supplied by B3, not free LLM synonym expansion.
- `Policy.publishedOnly` is explicit, and C1.0 filters out unpublished graph matches before grounding.
- Query transformation cache keys include corpus id, corpus version, and normalized query.
- Multi-query expansion is gated by low retrieval recall and does not run by default.
- C1 `Planner` transforms each decomposed subquery before C2 retrieval planning.
- The offline eval harness reports `recall@k`, MRR, citation accuracy, and abstention correctness.
- C5 gate correctness is exact for abstain, human-review, and conflict verdicts promoted into the golden set.
- C5 outcomes for abstain, human review, and conflict can be captured as labeled cases and promoted into the golden set after review.

## Current Boundaries

- The implementation is framework code plus Vitest coverage; it does not add a metrics dashboard.
- It does not tune embeddings, train a reranker, implement HyDE, or perform conversational multi-turn rewrite.
- Post-generation answer faithfulness remains a future C5b hook.
