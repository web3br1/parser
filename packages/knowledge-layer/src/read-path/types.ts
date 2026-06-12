export type RetrievalStrategy = "SQL" | "SEMANTIC" | "GRAPH";

export type ReadPathVerdict =
  | "sufficient"
  | "insufficient"
  | "abstain_required"
  | "human_review_required"
  | "conflict_detected";

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
  publishedOnly: boolean;
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
  published: boolean;
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
  verdict: ReadPathVerdict;
  reasons: string[];
  confidence: number;
}
