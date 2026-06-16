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

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function replaceGroundedTerm(query: string, match: GroundingMatch): string {
  const userTerm = normalizeQuery(match.userTerm);
  const corpusTerm = normalizeQuery(match.corpusTerm);

  if (!userTerm || !query.includes(userTerm)) {
    return query.includes(corpusTerm) ? query : `${query} ${corpusTerm}`;
  }

  const replaced = query.replace(new RegExp(escapeRegExp(userTerm), "g"), corpusTerm);
  return replaced.includes(corpusTerm) ? replaced : `${replaced} ${corpusTerm}`;
}

function stableCompare(left: string, right: string): number {
  if (left === right) return 0;
  return left < right ? -1 : 1;
}

function orderGrounding(matches: GroundingMatch[]): GroundingMatch[] {
  return [...matches].sort((left, right) => {
    const scoreDelta = right.score - left.score;
    if (scoreDelta !== 0) return scoreDelta;
    const entityDelta = stableCompare(left.entityId, right.entityId);
    if (entityDelta !== 0) return entityDelta;
    const corpusDelta = stableCompare(left.corpusTerm, right.corpusTerm);
    if (corpusDelta !== 0) return corpusDelta;
    return stableCompare(left.userTerm, right.userTerm);
  });
}

function publishedGrounding(matches: GroundingMatch[], policy: Policy): GroundingMatch[] {
  if (!policy.publishedOnly) return matches;
  return matches.filter((match) => match.published);
}

function cacheKeyFor(policy: Policy, rewrittenQuery: string): string {
  const visibility = policy.publishedOnly ? "published" : "all";
  return `${policy.corpusId}:${policy.corpusVersion}:${visibility}:${rewrittenQuery}`;
}

function cloneGroundingMatch(match: GroundingMatch): GroundingMatch {
  return { ...match };
}

function cloneTransformResult(result: QueryTransformResult): QueryTransformResult {
  return {
    ...result,
    grounding: result.grounding.map(cloneGroundingMatch),
    alternatives: [...result.alternatives],
  };
}

function applyGrounding(query: string, matches: GroundingMatch[]): string {
  return normalizeQuery(matches.reduce(replaceGroundedTerm, query));
}

function alternativesFromGrounding(query: string, matches: GroundingMatch[]): string[] {
  const seen = new Set<string>();
  const alternatives: string[] = [];

  for (const match of matches) {
    const alternative = normalizeQuery(replaceGroundedTerm(query, match));
    if (alternative && alternative !== query && !seen.has(alternative)) {
      alternatives.push(alternative);
      seen.add(alternative);
    }
  }

  return alternatives;
}

export class QueryTransformer {
  private readonly cache = new Map<string, QueryTransformResult>();

  constructor(private readonly deps: { graphTerms: GraphTermIndex }) {}

  async transformSubquery(query: string, policy: Policy): Promise<QueryTransformResult> {
    const rewrittenQuery = normalizeQuery(query);
    const cacheKey = cacheKeyFor(policy, rewrittenQuery);
    const cached = this.cache.get(cacheKey);
    if (cached) return cloneTransformResult(cached);

    const grounding = orderGrounding(publishedGrounding(
      await this.deps.graphTerms.lookupTerms(rewrittenQuery, policy),
      policy,
    ));
    const result: QueryTransformResult = {
      originalQuery: query,
      rewrittenQuery,
      groundedQuery: applyGrounding(rewrittenQuery, grounding),
      grounding: grounding.map(cloneGroundingMatch),
      alternatives: [],
      cacheKey,
    };

    this.cache.set(cacheKey, cloneTransformResult(result));
    return cloneTransformResult(result);
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
