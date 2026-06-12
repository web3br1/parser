import { describe, expect, it, vi } from "vitest";
import { Planner } from "./planner";
import type { Policy, QueryTransformResult } from "./types";

const policy: Policy = {
  corpusId: "quality-mgmt",
  corpusVersion: "ctx_001",
  publishedOnly: true,
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

  it("transforms each decomposed subquery before retrieval planning", async () => {
    const transformSubquery = vi.fn(async (query: string): Promise<QueryTransformResult> => ({
      originalQuery: query,
      rewrittenQuery: query,
      groundedQuery: `grounded:${query}`,
      grounding: [],
      alternatives: [],
      cacheKey: `ctx_001:${query}`,
    }));

    const planner = new Planner({
      queryTransformer: { transformSubquery },
      decomposer: {
        decompose: async () => [
          { id: "s1", query: "quem aprova capa", strategy: "SEMANTIC" },
          { id: "s2", query: "e prazo de resposta", strategy: "GRAPH", dependsOn: ["s1"] },
        ],
      },
    });

    const plan = await planner.plan("quem aprova capa e prazo de resposta", policy);

    expect(transformSubquery).toHaveBeenCalledTimes(2);
    expect(plan.steps.map((step) => step.query)).toEqual([
      "grounded:quem aprova capa",
      "grounded:e prazo de resposta",
    ]);
    expect(plan.steps[1].dependsOn).toEqual(["s1"]);
  });
});
