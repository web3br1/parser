# Read-Path Quality Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic query transformation and an offline eval/feedback harness for the Antigravity read-path.

**Architecture:** Implement T1 as a C1.0 `QueryTransformer` that rewrites each planned subquery, grounds vocabulary through the published graph index, and gates multi-query expansion on observed low recall. Implement T2 as a Vitest-driven golden-set harness plus a label capture store fed by C5 verdicts.

**Tech Stack:** TypeScript monorepo, Vitest, existing read-path contracts from `read-path-spec.md`; no Python or ML runtime changes.

---

## Target File Structure

- Create: `packages/knowledge-layer/src/read-path/types.ts`
  Shared read-path interfaces: `Plan`, `PlanStep`, `Policy`, `QueryTransformResult`, `RankedChunk`, `SufficiencyResult`, and eval types.
- Create: `packages/knowledge-layer/src/read-path/query-transformer.ts`
  Deterministic C1.0 query rewrite, graph-grounded vocabulary mapping, cache keying, and gated multi-query expansion.
- Create: `packages/knowledge-layer/src/read-path/query-transformer.test.ts`
  Vitest coverage for vocabulary hit, vocabulary miss, deterministic cache, plan-step integration, and multi-query gate.
- Modify: `packages/knowledge-layer/src/read-path/planner.ts`
  Call the transformer for each `PlanStep` before dispatching to C2.
- Test: `packages/knowledge-layer/src/read-path/planner.test.ts`
  Verify each decomposed step is transformed exactly once before retrieval.
- Create: `packages/knowledge-layer/src/read-path/eval/golden-set.ts`
  Golden case schema and starter fixtures.
- Create: `packages/knowledge-layer/src/read-path/eval/metrics.ts`
  Pure metric functions: `recallAtK`, `mrr`, `citationAccuracy`, `abstentionCorrectness`.
- Create: `packages/knowledge-layer/src/read-path/eval/harness.ts`
  Offline runner that executes read-path adapters against golden cases and returns metric reports.
- Create: `packages/knowledge-layer/src/read-path/eval/label-store.ts`
  Append-only labeled-case persistence boundary for C5 outcomes.
- Create: `packages/knowledge-layer/src/read-path/eval/harness.test.ts`
  Vitest coverage for metric reporting, policy delta visibility, abstention correctness, and label promotion.

---

## Task 1: Shared Read-Path Types

**Files:**
- Create: `packages/knowledge-layer/src/read-path/types.ts`

- [ ] **Step 1: Write shared contracts**

```ts
export type RetrievalStrategy = "SQL" | "SEMANTIC" | "GRAPH";

export interface Plan {
  steps: PlanStep[];
}

export interface PlanStep {
  id: string;
  strategy: RetrievalStrategy;
  query: string;
  required: boolean;
  scope: Record<string, unknown>;
  budget: {
    maxChunks?: number;
    maxTokens?: number;
    maxSections?: number;
  };
  dependsOn: string[];
}

export interface Policy {
  corpusId: string;
  corpusVersion: string;
  thresholds: {
    minStrongScore: number;
    minCoverageRatio: number;
    minCitationCoverage: number;
    confidenceFloor: number;
    lowRecallThreshold: number;
  };
  replanBudget: number;
}

export interface GroundingMatch {
  userTerm: string;
  corpusTerm: string;
  entityId: string;
  score: number;
}

export interface QueryTransformResult {
  originalQuery: string;
  rewrittenQuery: string;
  groundedQuery: string;
  grounding: GroundingMatch[];
  alternatives: string[];
  cacheKey: string;
}

export interface RankedChunk {
  chunkId: string;
  sourceId: string;
  sectionPath?: string;
  content: string;
  score: number;
  citations: Array<{ quote: string; evidenceSpanId?: string }>;
}

export interface SufficiencyResult {
  verdict: "sufficient" | "insufficient" | "abstain_required";
  reasons: string[];
  confidence: number;
}
```

- [ ] **Step 2: Run typecheck**

Run: `corepack pnpm --filter @antigravity/knowledge-layer typecheck`

Expected: fails only if the package does not exist yet; otherwise no type errors.

---

## Task 2: Query Transformer Red Tests

**Files:**
- Create: `packages/knowledge-layer/src/read-path/query-transformer.test.ts`
- Create: `packages/knowledge-layer/src/read-path/query-transformer.ts`

- [ ] **Step 1: Write failing tests**

```ts
import { describe, expect, it } from "vitest";
import { QueryTransformer } from "./query-transformer";
import type { GroundingMatch, Policy } from "./types";

const policy: Policy = {
  corpusId: "quality-mgmt",
  corpusVersion: "ctx_001",
  thresholds: {
    minStrongScore: 0.72,
    minCoverageRatio: 0.8,
    minCitationCoverage: 0.9,
    confidenceFloor: 0.75,
    lowRecallThreshold: 0.45,
  },
  replanBudget: 2,
};

function transformer(matches: GroundingMatch[]) {
  return new QueryTransformer({
    graphTerms: {
      lookupTerms: async () => matches,
    },
  });
}

describe("QueryTransformer", () => {
  it("grounds colloquial vocabulary to published corpus terms", async () => {
    const result = await transformer([
      { userTerm: "deu errado", corpusTerm: "não-conformidade", entityId: "ent_nc", score: 0.93 },
    ]).transformSubquery("deu errado na produção", policy);

    expect(result.rewrittenQuery).toBe("deu errado na produção");
    expect(result.groundedQuery).toContain("não-conformidade");
    expect(result.grounding[0].entityId).toBe("ent_nc");
  });

  it("does not invent corpus terms when graph grounding misses", async () => {
    const result = await transformer([]).transformSubquery("deu estranho", policy);

    expect(result.groundedQuery).toBe("deu estranho");
    expect(result.grounding).toEqual([]);
  });

  it("only emits multi-query alternatives after low recall", async () => {
    const qt = transformer([
      { userTerm: "como cancelo", corpusTerm: "rescisão", entityId: "ent_rescisao", score: 0.91 },
    ]);

    const highRecall = await qt.maybeExpandAfterRetrieval("como cancelo contrato", policy, {
      recallEstimate: 0.8,
    });
    const lowRecall = await qt.maybeExpandAfterRetrieval("como cancelo contrato", policy, {
      recallEstimate: 0.2,
    });

    expect(highRecall.alternatives).toEqual([]);
    expect(lowRecall.alternatives).toContain("rescisão contrato");
  });

  it("is deterministic for the same query and corpus version", async () => {
    const qt = transformer([
      { userTerm: "deu errado", corpusTerm: "não-conformidade", entityId: "ent_nc", score: 0.93 },
    ]);

    const first = await qt.transformSubquery("deu errado", policy);
    const second = await qt.transformSubquery("deu errado", policy);

    expect(second).toEqual(first);
    expect(first.cacheKey).toBe("ctx_001:deu errado");
  });
});
```

- [ ] **Step 2: Add compiling stub**

```ts
import type { GroundingMatch, Policy, QueryTransformResult } from "./types";

export interface GraphTermIndex {
  lookupTerms(query: string, policy: Policy): Promise<GroundingMatch[]>;
}

export interface RetrievalFeedback {
  recallEstimate: number;
}

export class QueryTransformer {
  constructor(private readonly deps: { graphTerms: GraphTermIndex }) {}

  async transformSubquery(query: string, policy: Policy): Promise<QueryTransformResult> {
    return {
      originalQuery: query,
      rewrittenQuery: query,
      groundedQuery: query,
      grounding: [],
      alternatives: [],
      cacheKey: `${policy.corpusVersion}:${query}`,
    };
  }

  async maybeExpandAfterRetrieval(
    query: string,
    policy: Policy,
    feedback: RetrievalFeedback,
  ): Promise<QueryTransformResult> {
    return this.transformSubquery(query, policy);
  }
}
```

- [ ] **Step 3: Run tests and verify RED**

Run: `corepack pnpm --filter @antigravity/knowledge-layer vitest run src/read-path/query-transformer.test.ts`

Expected: at least the vocabulary hit and low-recall expansion tests fail.

---

## Task 3: Query Transformer Implementation

**Files:**
- Modify: `packages/knowledge-layer/src/read-path/query-transformer.ts`

- [ ] **Step 1: Implement deterministic grounding**

```ts
import type { GroundingMatch, Policy, QueryTransformResult } from "./types";

export interface GraphTermIndex {
  lookupTerms(query: string, policy: Policy): Promise<GroundingMatch[]>;
}

export interface RetrievalFeedback {
  recallEstimate: number;
}

function normalizeQuery(query: string): string {
  return query.trim().replace(/\s+/g, " ").toLocaleLowerCase("pt-BR");
}

function applyGrounding(query: string, matches: GroundingMatch[]): string {
  let grounded = query;
  for (const match of matches) {
    if (!grounded.includes(match.corpusTerm)) {
      grounded = `${grounded} ${match.corpusTerm}`;
    }
  }
  return normalizeQuery(grounded);
}

function alternativesFromGrounding(query: string, matches: GroundingMatch[]): string[] {
  return matches
    .map((match) => normalizeQuery(`${match.corpusTerm} ${query}`))
    .filter((value, index, all) => value && all.indexOf(value) === index);
}

export class QueryTransformer {
  private readonly cache = new Map<string, QueryTransformResult>();

  constructor(private readonly deps: { graphTerms: GraphTermIndex }) {}

  async transformSubquery(query: string, policy: Policy): Promise<QueryTransformResult> {
    const rewrittenQuery = normalizeQuery(query);
    const cacheKey = `${policy.corpusVersion}:${rewrittenQuery}`;
    const cached = this.cache.get(cacheKey);
    if (cached) return cached;

    const grounding = await this.deps.graphTerms.lookupTerms(rewrittenQuery, policy);
    const result: QueryTransformResult = {
      originalQuery: query,
      rewrittenQuery,
      groundedQuery: applyGrounding(rewrittenQuery, grounding),
      grounding,
      alternatives: [],
      cacheKey,
    };
    this.cache.set(cacheKey, result);
    return result;
  }

  async maybeExpandAfterRetrieval(
    query: string,
    policy: Policy,
    feedback: RetrievalFeedback,
  ): Promise<QueryTransformResult> {
    const base = await this.transformSubquery(query, policy);
    if (feedback.recallEstimate >= policy.thresholds.lowRecallThreshold) {
      return base;
    }
    return {
      ...base,
      alternatives: alternativesFromGrounding(base.rewrittenQuery, base.grounding),
    };
  }
}
```

- [ ] **Step 2: Run tests and verify GREEN**

Run: `corepack pnpm --filter @antigravity/knowledge-layer vitest run src/read-path/query-transformer.test.ts`

Expected: all `QueryTransformer` tests pass.

---

## Task 4: Planner Integration

**Files:**
- Modify: `packages/knowledge-layer/src/read-path/planner.ts`
- Test: `packages/knowledge-layer/src/read-path/planner.test.ts`

- [ ] **Step 1: Write failing integration test**

```ts
import { describe, expect, it, vi } from "vitest";
import { Planner } from "./planner";
import type { Policy, QueryTransformResult } from "./types";

const policy: Policy = {
  corpusId: "quality-mgmt",
  corpusVersion: "ctx_001",
  thresholds: {
    minStrongScore: 0.72,
    minCoverageRatio: 0.8,
    minCitationCoverage: 0.9,
    confidenceFloor: 0.75,
    lowRecallThreshold: 0.45,
  },
  replanBudget: 2,
};

describe("Planner query transformation", () => {
  it("transforms every plan step before execution", async () => {
    const transformSubquery = vi.fn(async (query: string): Promise<QueryTransformResult> => ({
      originalQuery: query,
      rewrittenQuery: query,
      groundedQuery: `${query} não-conformidade`,
      grounding: [],
      alternatives: [],
      cacheKey: `ctx_001:${query}`,
    }));

    const planner = new Planner({
      queryTransformer: { transformSubquery },
    });

    const plan = await planner.plan("deu errado", policy);

    expect(transformSubquery).toHaveBeenCalledWith("deu errado", policy);
    expect(plan.steps[0].query).toBe("deu errado não-conformidade");
  });
});
```

- [ ] **Step 2: Implement minimal planner call**

```ts
import type { Plan, Policy, QueryTransformResult } from "./types";

export interface QueryTransformerPort {
  transformSubquery(query: string, policy: Policy): Promise<QueryTransformResult>;
}

export class Planner {
  constructor(private readonly deps: { queryTransformer: QueryTransformerPort }) {}

  async plan(query: string, policy: Policy): Promise<Plan> {
    const transformed = await this.deps.queryTransformer.transformSubquery(query, policy);
    return {
      steps: [{
        id: "s1",
        strategy: "SEMANTIC",
        query: transformed.groundedQuery,
        required: true,
        scope: { grounding: transformed.grounding },
        budget: { maxChunks: 4, maxTokens: 2400 },
        dependsOn: [],
      }],
    };
  }
}
```

- [ ] **Step 3: Run planner test**

Run: `corepack pnpm --filter @antigravity/knowledge-layer vitest run src/read-path/planner.test.ts`

Expected: planner transformation test passes.

---

## Task 5: Golden Set And Metrics

**Files:**
- Create: `packages/knowledge-layer/src/read-path/eval/golden-set.ts`
- Create: `packages/knowledge-layer/src/read-path/eval/metrics.ts`
- Test: `packages/knowledge-layer/src/read-path/eval/harness.test.ts`

- [ ] **Step 1: Define golden-case schema**

```ts
export interface GoldenCase {
  id: string;
  query: string;
  expectedChunkIds: string[];
  expectedCitationQuotes: string[];
  expectedVerdict: "sufficient" | "insufficient" | "abstain_required";
}

export const starterGoldenSet: GoldenCase[] = [
  {
    id: "capa-approval",
    query: "Quem aprova CAPA crítica?",
    expectedChunkIds: ["chunk_capa_approval"],
    expectedCitationQuotes: ["Gerente da Qualidade deve aprovar CAPA crítica"],
    expectedVerdict: "sufficient",
  },
  {
    id: "unknown-policy",
    query: "Qual a regra para benefício não documentado?",
    expectedChunkIds: [],
    expectedCitationQuotes: [],
    expectedVerdict: "abstain_required",
  },
];
```

- [ ] **Step 2: Implement pure metrics**

```ts
import type { GoldenCase } from "./golden-set";
import type { RankedChunk, SufficiencyResult } from "../types";

export function recallAtK(expectedIds: string[], actualIds: string[], k: number): number {
  if (expectedIds.length === 0) return actualIds.length === 0 ? 1 : 0;
  const topK = new Set(actualIds.slice(0, k));
  const hits = expectedIds.filter((id) => topK.has(id)).length;
  return hits / expectedIds.length;
}

export function mrr(expectedIds: string[], actualIds: string[]): number {
  for (let index = 0; index < actualIds.length; index += 1) {
    if (expectedIds.includes(actualIds[index])) return 1 / (index + 1);
  }
  return expectedIds.length === 0 ? 1 : 0;
}

export function citationAccuracy(expectedQuotes: string[], chunks: RankedChunk[]): number {
  if (expectedQuotes.length === 0) return chunks.every((chunk) => chunk.citations.length === 0) ? 1 : 0;
  const actualQuotes = chunks.flatMap((chunk) => chunk.citations.map((citation) => citation.quote));
  const hits = expectedQuotes.filter((quote) => actualQuotes.some((actual) => actual.includes(quote))).length;
  return hits / expectedQuotes.length;
}

export function abstentionCorrectness(testCase: GoldenCase, result: SufficiencyResult): number {
  const expectedAbstain = testCase.expectedVerdict === "abstain_required";
  const actualAbstain = result.verdict === "abstain_required";
  return expectedAbstain === actualAbstain ? 1 : 0;
}
```

- [ ] **Step 3: Write metric tests**

```ts
import { describe, expect, it } from "vitest";
import { abstentionCorrectness, citationAccuracy, mrr, recallAtK } from "./metrics";

describe("read-path eval metrics", () => {
  it("computes retrieval metrics", () => {
    expect(recallAtK(["a", "b"], ["x", "a", "b"], 2)).toBe(0.5);
    expect(mrr(["b"], ["a", "b"])).toBe(0.5);
  });

  it("computes citation accuracy", () => {
    expect(citationAccuracy(["texto aprovado"], [{
      chunkId: "c1",
      sourceId: "s1",
      content: "texto",
      score: 0.9,
      citations: [{ quote: "texto aprovado literal" }],
    }])).toBe(1);
  });

  it("distinguishes correct and wrong abstention", () => {
    expect(abstentionCorrectness({
      id: "missing",
      query: "sem base",
      expectedChunkIds: [],
      expectedCitationQuotes: [],
      expectedVerdict: "abstain_required",
    }, { verdict: "abstain_required", reasons: ["published_context_absent"], confidence: 1 })).toBe(1);
  });
});
```

- [ ] **Step 4: Run tests**

Run: `corepack pnpm --filter @antigravity/knowledge-layer vitest run src/read-path/eval/harness.test.ts`

Expected: metric tests pass.

---

## Task 6: Offline Harness And Policy Delta

**Files:**
- Create: `packages/knowledge-layer/src/read-path/eval/harness.ts`
- Modify: `packages/knowledge-layer/src/read-path/eval/harness.test.ts`

- [ ] **Step 1: Implement harness**

```ts
import type { GoldenCase } from "./golden-set";
import { abstentionCorrectness, citationAccuracy, mrr, recallAtK } from "./metrics";
import type { Policy, RankedChunk, SufficiencyResult } from "../types";

export interface ReadPathEvalAdapter {
  run(query: string, policy: Policy): Promise<{
    chunks: RankedChunk[];
    sufficiency: SufficiencyResult;
  }>;
}

export interface EvalReport {
  recallAtK: number;
  mrr: number;
  citationAccuracy: number;
  abstentionCorrectness: number;
}

export async function runGoldenSet(
  cases: GoldenCase[],
  adapter: ReadPathEvalAdapter,
  policy: Policy,
  k = 5,
): Promise<EvalReport> {
  const rows = await Promise.all(cases.map(async (testCase) => {
    const result = await adapter.run(testCase.query, policy);
    const actualIds = result.chunks.map((chunk) => chunk.chunkId);
    return {
      recallAtK: recallAtK(testCase.expectedChunkIds, actualIds, k),
      mrr: mrr(testCase.expectedChunkIds, actualIds),
      citationAccuracy: citationAccuracy(testCase.expectedCitationQuotes, result.chunks),
      abstentionCorrectness: abstentionCorrectness(testCase, result.sufficiency),
    };
  }));

  return {
    recallAtK: average(rows.map((row) => row.recallAtK)),
    mrr: average(rows.map((row) => row.mrr)),
    citationAccuracy: average(rows.map((row) => row.citationAccuracy)),
    abstentionCorrectness: average(rows.map((row) => row.abstentionCorrectness)),
  };
}

function average(values: number[]): number {
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}
```

- [ ] **Step 2: Add harness tests**

```ts
import { describe, expect, it } from "vitest";
import { runGoldenSet } from "./harness";
import type { Policy } from "../types";

const policy: Policy = {
  corpusId: "quality-mgmt",
  corpusVersion: "ctx_001",
  thresholds: {
    minStrongScore: 0.7,
    minCoverageRatio: 0.8,
    minCitationCoverage: 0.9,
    confidenceFloor: 0.75,
    lowRecallThreshold: 0.45,
  },
  replanBudget: 2,
};

describe("runGoldenSet", () => {
  it("reports all four metrics", async () => {
    const report = await runGoldenSet([{
      id: "case",
      query: "Quem aprova CAPA crítica?",
      expectedChunkIds: ["chunk_capa"],
      expectedCitationQuotes: ["Gerente da Qualidade"],
      expectedVerdict: "sufficient",
    }], {
      async run() {
        return {
          chunks: [{
            chunkId: "chunk_capa",
            sourceId: "source_1",
            content: "Gerente da Qualidade deve aprovar CAPA crítica",
            score: 0.9,
            citations: [{ quote: "Gerente da Qualidade deve aprovar CAPA crítica" }],
          }],
          sufficiency: { verdict: "sufficient", reasons: [], confidence: 0.9 },
        };
      },
    }, policy);

    expect(report).toEqual({
      recallAtK: 1,
      mrr: 1,
      citationAccuracy: 1,
      abstentionCorrectness: 1,
    });
  });

  it("makes policy changes measurable", async () => {
    const strictPolicy = { ...policy, thresholds: { ...policy.thresholds, minStrongScore: 0.95 } };
    const loosePolicy = { ...policy, thresholds: { ...policy.thresholds, minStrongScore: 0.5 } };
    const adapter = {
      async run(_query: string, activePolicy: Policy) {
        const pass = activePolicy.thresholds.minStrongScore < 0.9;
        return {
          chunks: pass ? [{
            chunkId: "chunk_capa",
            sourceId: "source_1",
            content: "Gerente da Qualidade deve aprovar CAPA crítica",
            score: 0.9,
            citations: [{ quote: "Gerente da Qualidade deve aprovar CAPA crítica" }],
          }] : [],
          sufficiency: pass
            ? { verdict: "sufficient" as const, reasons: [], confidence: 0.9 }
            : { verdict: "abstain_required" as const, reasons: ["low_retrieval_groundedness"], confidence: 0.4 },
        };
      },
    };

    const strictReport = await runGoldenSet([{
      id: "case",
      query: "Quem aprova CAPA crítica?",
      expectedChunkIds: ["chunk_capa"],
      expectedCitationQuotes: ["Gerente da Qualidade"],
      expectedVerdict: "sufficient",
    }], adapter, strictPolicy);
    const looseReport = await runGoldenSet([{
      id: "case",
      query: "Quem aprova CAPA crítica?",
      expectedChunkIds: ["chunk_capa"],
      expectedCitationQuotes: ["Gerente da Qualidade"],
      expectedVerdict: "sufficient",
    }], adapter, loosePolicy);

    expect(looseReport.recallAtK).toBeGreaterThan(strictReport.recallAtK);
  });
});
```

- [ ] **Step 3: Run harness tests**

Run: `corepack pnpm --filter @antigravity/knowledge-layer vitest run src/read-path/eval/harness.test.ts`

Expected: all harness tests pass.

---

## Task 7: C5 Label Capture And Golden Promotion

**Files:**
- Create: `packages/knowledge-layer/src/read-path/eval/label-store.ts`
- Test: `packages/knowledge-layer/src/read-path/eval/label-store.test.ts`

- [ ] **Step 1: Implement label store boundary**

```ts
import type { GoldenCase } from "./golden-set";
import type { SufficiencyResult } from "../types";

export interface LabeledCase {
  id: string;
  query: string;
  contextHash: string;
  verdict: SufficiencyResult["verdict"];
  reasons: string[];
  createdAt: string;
  reviewed: boolean;
}

export class InMemoryLabelStore {
  private readonly cases: LabeledCase[] = [];

  capture(input: Omit<LabeledCase, "id" | "createdAt" | "reviewed">): LabeledCase {
    const row: LabeledCase = {
      ...input,
      id: `label_${this.cases.length + 1}`,
      createdAt: "stable-test-time",
      reviewed: false,
    };
    this.cases.push(row);
    return row;
  }

  listUnreviewed(): LabeledCase[] {
    return this.cases.filter((row) => !row.reviewed);
  }

  promoteToGolden(labelId: string, expectedChunkIds: string[], expectedCitationQuotes: string[]): GoldenCase {
    const row = this.cases.find((item) => item.id === labelId);
    if (!row) throw new Error(`label not found: ${labelId}`);
    row.reviewed = true;
    return {
      id: row.id,
      query: row.query,
      expectedChunkIds,
      expectedCitationQuotes,
      expectedVerdict: row.verdict,
    };
  }
}
```

- [ ] **Step 2: Test capture and promotion**

```ts
import { describe, expect, it } from "vitest";
import { InMemoryLabelStore } from "./label-store";

describe("InMemoryLabelStore", () => {
  it("persists C5 abstain/human/conflict cases as labels", () => {
    const store = new InMemoryLabelStore();

    const captured = store.capture({
      query: "Qual regra não publicada posso usar?",
      contextHash: "ctx_hash",
      verdict: "abstain_required",
      reasons: ["published_context_absent"],
    });

    expect(captured.id).toBe("label_1");
    expect(store.listUnreviewed()).toHaveLength(1);
  });

  it("promotes a reviewed labeled case into the golden set shape", () => {
    const store = new InMemoryLabelStore();
    const captured = store.capture({
      query: "Quem aprova CAPA crítica?",
      contextHash: "ctx_hash",
      verdict: "sufficient",
      reasons: [],
    });

    const golden = store.promoteToGolden(
      captured.id,
      ["chunk_capa"],
      ["Gerente da Qualidade deve aprovar CAPA crítica"],
    );

    expect(golden.expectedChunkIds).toEqual(["chunk_capa"]);
    expect(store.listUnreviewed()).toHaveLength(0);
  });
});
```

- [ ] **Step 3: Run label tests**

Run: `corepack pnpm --filter @antigravity/knowledge-layer vitest run src/read-path/eval/label-store.test.ts`

Expected: all label-store tests pass.

---

## Task 8: Verification Gate

**Files:**
- No new files.

- [ ] **Step 1: Run focused tests**

Run:

```bash
corepack pnpm --filter @antigravity/knowledge-layer vitest run \
  src/read-path/query-transformer.test.ts \
  src/read-path/planner.test.ts \
  src/read-path/eval/harness.test.ts \
  src/read-path/eval/label-store.test.ts
```

Expected: all focused read-path quality tests pass.

- [ ] **Step 2: Run typecheck**

Run: `corepack pnpm --filter @antigravity/knowledge-layer typecheck`

Expected: no TypeScript errors.

- [ ] **Step 3: Document implementation notes**

Append the implementation status to `docs/read-path-quality.md` or the project’s equivalent read-path notes file:

```markdown
## Read-Path Quality Improvements

- C1.0 QueryTransformer rewrites and grounds subqueries through published graph terms.
- Multi-query expansion is gated by low recall.
- Eval harness reports recall@k, MRR, citation accuracy, and abstention correctness.
- C5 abstain/human/conflict outcomes can be captured as labeled cases and promoted to the golden set after review.
```

Expected: documentation reflects the new quality loop without claiming dashboard, fine-tuning, or post-generation faithfulness support.

---

## Self-Review

- T1 coverage: query rewrite, graph-grounding, multi-query gate, deterministic cache, plan-step transformation, Vitest cases.
- T2 coverage: golden set, offline metrics, measurable policy deltas, abstention correctness, C5 label capture, promotion path.
- Scope kept out: HyDE, embedding fine-tuning, multi-turn rewrite, metrics dashboard, reranker training, C5b answer faithfulness.
- Implementation caveat: this plan targets the Antigravity TypeScript monorepo. The current Parser repo has a Python read-path, so execution should happen in the Antigravity package or after creating `packages/knowledge-layer`.
