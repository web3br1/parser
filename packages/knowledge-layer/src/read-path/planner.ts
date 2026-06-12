import type { Plan, PlanStep, Policy, QueryTransformResult, RetrievalStrategy } from "./types";

export interface QueryTransformerPort {
  transformSubquery(query: string, policy: Policy): Promise<QueryTransformResult>;
}

export interface PlanStepDraft {
  id?: string;
  strategy?: RetrievalStrategy;
  query: string;
  required?: boolean;
  scope?: Record<string, unknown>;
  budget?: PlanStep["budget"];
  dependsOn?: string[];
}

export interface DecomposerPort {
  decompose(query: string, policy: Policy): Promise<PlanStepDraft[]>;
}

export class Planner {
  constructor(
    private readonly deps: {
      queryTransformer: QueryTransformerPort;
      decomposer?: DecomposerPort;
    },
  ) {}

  async plan(query: string, policy: Policy): Promise<Plan> {
    const drafts = await this.decompose(query, policy);
    const steps = await Promise.all(
      drafts.map(async (draft, index): Promise<PlanStep> => {
        const transformed = await this.deps.queryTransformer.transformSubquery(draft.query, policy);
        return {
          id: draft.id ?? `s${index + 1}`,
          strategy: draft.strategy ?? "SEMANTIC",
          query: transformed.groundedQuery,
          required: draft.required ?? true,
          scope: {
            ...(draft.scope ?? {}),
            grounding: transformed.grounding,
            queryTransformCacheKey: transformed.cacheKey,
          },
          budget: draft.budget ?? { maxChunks: 4, maxTokens: 2400 },
          dependsOn: draft.dependsOn ?? [],
        };
      }),
    );

    return { steps };
  }

  private async decompose(query: string, policy: Policy): Promise<PlanStepDraft[]> {
    if (this.deps.decomposer) {
      return this.deps.decomposer.decompose(query, policy);
    }

    return [{ query }];
  }
}
