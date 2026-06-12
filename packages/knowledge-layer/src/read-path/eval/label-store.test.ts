import { describe, expect, it } from "vitest";
import { InMemoryLabelStore } from "./label-store";

describe("InMemoryLabelStore", () => {
  it("persists C5 abstain, human-review, and conflict cases as labels", () => {
    const store = new InMemoryLabelStore(() => "stable-test-time");

    const abstain = store.capture({
      query: "Qual regra não publicada posso usar?",
      contextHash: "ctx_hash_1",
      context: { chunkIds: [], citationQuotes: [] },
      verdict: "abstain_required",
      reasons: ["published_context_absent"],
    });
    const human = store.capture({
      query: "Posso liberar exceção sem aprovação?",
      contextHash: "ctx_hash_2",
      context: { chunkIds: ["chunk_policy"], citationQuotes: ["Exceções exigem aprovação"] },
      verdict: "human_review_required",
      reasons: ["policy_exception_requires_approval"],
    });
    const conflict = store.capture({
      query: "Qual prazo vigente?",
      contextHash: "ctx_hash_3",
      context: { chunkIds: ["old", "new"], citationQuotes: ["5 dias", "10 dias"] },
      verdict: "conflict_detected",
      reasons: ["conflicting_versions"],
    });

    expect(abstain.id).toBe("label_1");
    expect(human.verdict).toBe("human_review_required");
    expect(conflict.context.chunkIds).toEqual(["old", "new"]);
    expect(store.listUnreviewed()).toHaveLength(3);
  });

  it("promotes a reviewed labeled case into the golden set shape", () => {
    const store = new InMemoryLabelStore(() => "stable-test-time");
    const captured = store.capture({
      query: "Quem aprova CAPA crítica?",
      contextHash: "ctx_hash",
      context: { chunkIds: ["chunk_capa"], citationQuotes: ["Gerente da Qualidade"] },
      verdict: "sufficient",
      reasons: [],
    });

    const golden = store.promoteToGolden(
      captured.id,
      ["chunk_capa"],
      ["Gerente da Qualidade deve aprovar CAPA crítica"],
    );

    expect(golden.expectedChunkIds).toEqual(["chunk_capa"]);
    expect(golden.expectedVerdict).toBe("sufficient");
    expect(store.listUnreviewed()).toHaveLength(0);
  });
});
