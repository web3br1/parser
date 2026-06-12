import type { GoldenCase } from "./golden-set";
import type { RankedChunk, SufficiencyResult } from "../types";

export function recallAtK(expectedIds: string[], actualIds: string[], k: number): number {
  if (expectedIds.length === 0) {
    return actualIds.length === 0 ? 1 : 0;
  }

  const topK = new Set(actualIds.slice(0, k));
  const hits = expectedIds.filter((id) => topK.has(id)).length;
  return hits / expectedIds.length;
}

export function mrr(expectedIds: string[], actualIds: string[]): number {
  for (let index = 0; index < actualIds.length; index += 1) {
    if (expectedIds.includes(actualIds[index])) {
      return 1 / (index + 1);
    }
  }

  return expectedIds.length === 0 ? 1 : 0;
}

export function citationAccuracy(expectedQuotes: string[], chunks: RankedChunk[]): number {
  if (expectedQuotes.length === 0) {
    return chunks.every((chunk) => chunk.citations.length === 0) ? 1 : 0;
  }

  const actualQuotes = chunks.flatMap((chunk) => chunk.citations.map((citation) => citation.quote));
  const hits = expectedQuotes.filter((quote) =>
    actualQuotes.some((actual) => actual.includes(quote)),
  ).length;

  return hits / expectedQuotes.length;
}

export function abstentionCorrectness(testCase: GoldenCase, result: SufficiencyResult): number {
  return testCase.expectedVerdict === result.verdict ? 1 : 0;
}
