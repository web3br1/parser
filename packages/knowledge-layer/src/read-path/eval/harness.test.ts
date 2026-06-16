import { describe, expect, it } from "vitest";
import { runGoldenSet } from "./harness";
import { abstentionCorrectness, citationAccuracy, mrr, recallAtK } from "./metrics";
import type { Policy } from "../types";

const policy: Policy = {
  corpusId: "quality-mgmt",
  corpusVersion: "ctx_001",
  publishedOnly: true,
  thresholds: {
    minStrongScore: 0.7,
    minCoverageRatio: 0.8,
    minCitationCoverage: 0.9,
    confidenceFloor: 0.75,
    lowRecallThreshold: 0.45,
  },
  replanBudget: 2,
};

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

  it("distinguishes correct and wrong C5 gate verdicts", () => {
    const missingCase = {
      id: "missing",
      query: "sem base",
      expectedChunkIds: [],
      expectedCitationQuotes: [],
      expectedVerdict: "abstain_required" as const,
    };

    expect(abstentionCorrectness(missingCase, {
      verdict: "abstain_required",
      reasons: ["published_context_absent"],
      confidence: 1,
    })).toBe(1);
    expect(abstentionCorrectness(missingCase, {
      verdict: "sufficient",
      reasons: [],
      confidence: 0.8,
    })).toBe(0);

    const humanReviewCase = {
      id: "human",
      query: "exceção",
      expectedChunkIds: ["policy"],
      expectedCitationQuotes: ["Exceções exigem aprovação"],
      expectedVerdict: "human_review_required" as const,
    };

    expect(abstentionCorrectness(humanReviewCase, {
      verdict: "human_review_required",
      reasons: ["policy_exception_requires_approval"],
      confidence: 0.7,
    })).toBe(1);
    expect(abstentionCorrectness(humanReviewCase, {
      verdict: "sufficient",
      reasons: [],
      confidence: 0.9,
    })).toBe(0);

    const conflictCase = {
      id: "conflict",
      query: "prazo vigente",
      expectedChunkIds: ["old", "new"],
      expectedCitationQuotes: ["5 dias", "10 dias"],
      expectedVerdict: "conflict_detected" as const,
    };

    expect(abstentionCorrectness(conflictCase, {
      verdict: "conflict_detected",
      reasons: ["conflicting_versions"],
      confidence: 0.5,
    })).toBe(1);
    expect(abstentionCorrectness(conflictCase, {
      verdict: "sufficient",
      reasons: [],
      confidence: 0.9,
    })).toBe(0);
  });
});

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

    const cases = [{
      id: "case",
      query: "Quem aprova CAPA crítica?",
      expectedChunkIds: ["chunk_capa"],
      expectedCitationQuotes: ["Gerente da Qualidade"],
      expectedVerdict: "sufficient" as const,
    }];

    const strictReport = await runGoldenSet(cases, adapter, strictPolicy);
    const looseReport = await runGoldenSet(cases, adapter, loosePolicy);

    expect(looseReport.recallAtK).toBeGreaterThan(strictReport.recallAtK);
    expect(looseReport.abstentionCorrectness).toBeGreaterThan(strictReport.abstentionCorrectness);
  });
});
