import type { Policy, RankedChunk, SufficiencyResult } from "../types";
import type { GoldenCase } from "./golden-set";
import { abstentionCorrectness, citationAccuracy, mrr, recallAtK } from "./metrics";

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
  if (values.length === 0) return 0;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}
