import { describe, expect, it } from "vitest";
import { QueryTransformer } from "./query-transformer";
import type { GroundingMatch, Policy } from "./types";

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
      {
        userTerm: "deu errado",
        corpusTerm: "não-conformidade",
        entityId: "ent_nc",
        score: 0.93,
        published: true,
      },
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
      {
        userTerm: "como cancelo",
        corpusTerm: "rescisão",
        entityId: "ent_rescisao",
        score: 0.91,
        published: true,
      },
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
      {
        userTerm: "deu errado",
        corpusTerm: "não-conformidade",
        entityId: "ent_nc",
        score: 0.93,
        published: true,
      },
    ]);

    const first = await qt.transformSubquery("deu errado", policy);
    const second = await qt.transformSubquery("deu errado", policy);

    expect(second).toEqual(first);
    expect(first.cacheKey).toBe("quality-mgmt:ctx_001:published:deu errado");
  });

  it("does not apply unpublished graph matches when published_only is required", async () => {
    const result = await transformer([
      {
        userTerm: "deu errado",
        corpusTerm: "rascunho-interno",
        entityId: "ent_draft",
        score: 0.99,
        published: false,
      },
    ]).transformSubquery("deu errado", policy);

    expect(result.groundedQuery).toBe("deu errado");
    expect(result.grounding).toEqual([]);
  });

  it("isolates cache entries by corpus id as well as version", async () => {
    const qt = new QueryTransformer({
      graphTerms: {
        lookupTerms: async (_query, activePolicy) => [{
          userTerm: "como cancelo",
          corpusTerm: activePolicy.corpusId === "quality-mgmt" ? "rescisão" : "cancelamento",
          entityId: activePolicy.corpusId,
          score: 0.9,
          published: true,
        }],
      },
    });

    const quality = await qt.transformSubquery("como cancelo", policy);
    const legal = await qt.transformSubquery("como cancelo", {
      ...policy,
      corpusId: "legal",
    });

    expect(quality.groundedQuery).toBe("rescisão");
    expect(legal.groundedQuery).toBe("cancelamento");
  });

  it("partitions cache by published_only policy", async () => {
    const qt = transformer([
      {
        userTerm: "rascunho",
        corpusTerm: "termo-nao-publicado",
        entityId: "draft",
        score: 0.99,
        published: false,
      },
    ]);

    const permissive = await qt.transformSubquery("rascunho", {
      ...policy,
      publishedOnly: false,
    });
    const publishedOnly = await qt.transformSubquery("rascunho", policy);

    expect(permissive.groundedQuery).toBe("termo-nao-publicado");
    expect(permissive.cacheKey).toBe("quality-mgmt:ctx_001:all:rascunho");
    expect(publishedOnly.groundedQuery).toBe("rascunho");
    expect(publishedOnly.grounding).toEqual([]);
    expect(publishedOnly.cacheKey).toBe("quality-mgmt:ctx_001:published:rascunho");
  });

  it("returns copies so caller mutations do not poison cached results", async () => {
    const qt = transformer([
      {
        userTerm: "deu errado",
        corpusTerm: "não-conformidade",
        entityId: "ent_nc",
        score: 0.93,
        published: true,
      },
    ]);

    const first = await qt.transformSubquery("deu errado", policy);
    first.grounding.push({
      userTerm: "poison",
      corpusTerm: "poison",
      entityId: "poison",
      score: 1,
      published: true,
    });
    first.alternatives.push("poison");

    const second = await qt.transformSubquery("deu errado", policy);

    expect(second.grounding).toHaveLength(1);
    expect(second.alternatives).toEqual([]);
  });

  it("orders equal-score grounding matches deterministically", async () => {
    const result = await transformer([
      {
        userTerm: "z termo",
        corpusTerm: "zeta",
        entityId: "ent_same",
        score: 0.8,
        published: true,
      },
      {
        userTerm: "a termo",
        corpusTerm: "alpha",
        entityId: "ent_same",
        score: 0.8,
        published: true,
      },
    ]).transformSubquery("consulta", policy);

    expect(result.grounding.map((match) => match.corpusTerm)).toEqual(["alpha", "zeta"]);
  });
});
