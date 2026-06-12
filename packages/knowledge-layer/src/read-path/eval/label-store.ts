import type { GoldenCase } from "./golden-set";
import type { ReadPathVerdict } from "../types";

export interface LabeledContext {
  chunkIds: string[];
  citationQuotes: string[];
}

export interface LabeledCase {
  id: string;
  query: string;
  contextHash: string;
  context: LabeledContext;
  verdict: ReadPathVerdict;
  reasons: string[];
  createdAt: string;
  reviewed: boolean;
}

export class InMemoryLabelStore {
  private readonly cases: LabeledCase[] = [];

  constructor(private readonly now: () => string = () => new Date().toISOString()) {}

  capture(input: Omit<LabeledCase, "id" | "createdAt" | "reviewed">): LabeledCase {
    const row: LabeledCase = {
      ...input,
      context: {
        chunkIds: [...input.context.chunkIds],
        citationQuotes: [...input.context.citationQuotes],
      },
      reasons: [...input.reasons],
      id: `label_${this.cases.length + 1}`,
      createdAt: this.now(),
      reviewed: false,
    };

    this.cases.push(row);
    return cloneCase(row);
  }

  listUnreviewed(): LabeledCase[] {
    return this.cases.filter((row) => !row.reviewed).map(cloneCase);
  }

  promoteToGolden(
    labelId: string,
    expectedChunkIds: string[],
    expectedCitationQuotes: string[],
  ): GoldenCase {
    const row = this.cases.find((item) => item.id === labelId);
    if (!row) {
      throw new Error(`label not found: ${labelId}`);
    }

    row.reviewed = true;
    return {
      id: row.id,
      query: row.query,
      expectedChunkIds: [...expectedChunkIds],
      expectedCitationQuotes: [...expectedCitationQuotes],
      expectedVerdict: row.verdict,
    };
  }
}

function cloneCase(row: LabeledCase): LabeledCase {
  return {
    ...row,
    context: {
      chunkIds: [...row.context.chunkIds],
      citationQuotes: [...row.context.citationQuotes],
    },
    reasons: [...row.reasons],
  };
}
