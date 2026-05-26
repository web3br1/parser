export type ApiErrorDetail =
  | string
  | Array<{
      loc?: unknown[];
      msg?: string;
      type?: string;
      [key: string]: unknown;
    }>
  | {
      code?: string;
      reason?: string;
      existing_source_id?: string | null;
      existing_status?: string | null;
      expected?: unknown;
      current?: unknown;
      valid?: unknown;
      [key: string]: unknown;
    };

export class ApiError extends Error {
  status: number;
  detail: ApiErrorDetail | null;

  constructor(status: number, detail: ApiErrorDetail | null) {
    super(apiErrorTitle(status, detail));
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

function apiErrorTitle(status: number, detail: ApiErrorDetail | null): string {
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    return detail[0]?.msg ?? `Request failed with ${status}`;
  }
  return detail?.code ?? `Request failed with ${status}`;
}

const DEFAULT_API_BASE_URL = "http://localhost:8000";

function resolveApiBaseUrl(): string {
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (!configured) {
    return DEFAULT_API_BASE_URL;
  }

  return configured.replace(/\/+$/, "") || DEFAULT_API_BASE_URL;
}

export const API_BASE_URL = resolveApiBaseUrl();

export async function apiFetch<T>(
  path: string,
  options: RequestInit & { token: string }
): Promise<T> {
  const { token, headers, ...requestOptions } = options;
  const requestHeaders = new Headers(headers);
  requestHeaders.set("Authorization", `Bearer ${token}`);

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...requestOptions,
    headers: requestHeaders
  });

  if (!response.ok) {
    let detail: ApiErrorDetail | null = null;
    try {
      const payload = (await response.json()) as { detail?: ApiErrorDetail };
      detail = payload.detail ?? null;
    } catch {
      detail = response.statusText;
    }
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export function apiMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (Array.isArray(error.detail)) {
      const first = error.detail[0];
      return first?.msg ?? `Request failed with ${error.status}.`;
    }
    if (typeof error.detail === "object" && error.detail) {
      if (error.detail.code === "duplicate_file") {
        return `Duplicate file. Existing source ${error.detail.existing_source_id ?? "unknown"} is ${error.detail.existing_status ?? "active"}.`;
      }
      if (error.detail.code === "file_validation_failed") {
        return `Validation rejected: ${error.detail.reason ?? "unknown reason"}.`;
      }
      if (error.detail.code === "invalid_destination_for_fact_type") {
        return `Invalid destination for fact type. Expected ${formatApiValue(error.detail.expected)}, got ${formatApiValue(error.detail.current)}.`;
      }
      if (error.detail.code === "insufficient_role") {
        return `Insufficient role. Required: ${formatApiValue(error.detail.required)}. Current: ${formatApiValue(error.detail.current)}.`;
      }
      if (error.detail.code === "invalid_fact_type" || error.detail.code === "invalid_destination") {
        return `${error.detail.code}: valid values are ${formatApiValue(error.detail.valid)}.`;
      }
      if (error.detail.code === "already_mapped" || error.detail.code === "already_ignored") {
        return `${error.detail.code}: this item has already been resolved.`;
      }
      if (error.detail.code === "validation_error") {
        return `Validation error: ${formatApiValue(error.detail.errors)}`;
      }
      if (typeof error.detail.code === "string" && error.detail.code.startsWith("invalid_")) {
        return `${error.detail.code}: ${formatApiValue(error.detail.detail)}`;
      }
      if (typeof error.detail.code === "string" && error.detail.code.includes("open_contradiction")) {
        return `${error.detail.code}: resolve the contradiction before publishing.`;
      }
      return error.detail.code ?? `Request failed with ${error.status}.`;
    }
    if (error.detail === "file_too_large") {
      return "File too large for the configured upload limit.";
    }
    return error.detail ?? `Request failed with ${error.status}.`;
  }
  return error instanceof Error ? error.message : "Unexpected error.";
}

function formatApiValue(value: unknown): string {
  if (Array.isArray(value)) {
    return value.map((item) => String(item)).join(", ");
  }
  if (value === null || value === undefined) {
    return "unknown";
  }
  return String(value);
}

export type Workspace = {
  id: string;
  name: string;
  slug: string | null;
  status: string;
  created_at: string;
};

export type Source = {
  id: string;
  workspace_id: string;
  status: string;
  title: string | null;
  original_filename: string | null;
  mime_type: string | null;
  file_size_bytes: number | null;
  created_at: string;
};

export type UploadResponse = {
  source_id: string;
  job_id: string;
  status: string;
  message: string;
};

export type ContextBuildFileMetadata = {
  name: string;
  size: number;
  relative_path: string | null;
  mime_type: string | null;
  last_modified: number | null;
};

export type ContextBuildPreflightRequest = {
  files?: ContextBuildFileMetadata[];
  staged_upload_id?: string | null;
  input_fingerprint?: string | null;
  input_hash?: string | null;
  persist?: boolean;
};

export type ContextBuildPreflightResponse = {
  run_id: string | null;
  input_mode: "single_document" | "multi_document_batch" | "source_pack";
  status: string;
  recommended_action: "compile_as_source_pack" | "normal_ingest" | "batch_ingest" | "reject" | string;
  input_fingerprint: string;
  input_hash: string | null;
  source_pack_id: string | null;
  source_pack_version: string | null;
  counts: Record<string, number>;
  missing_files: string[];
  extra_files: string[];
  warnings: string[];
  errors: string[];
  blocking_reasons: string[];
  metadata?: Record<string, unknown> | null;
};

export type ContextBuildStagedUploadResponse = {
  staged_upload_id: string;
  input_hash: string;
  input_fingerprint: string;
  files: ContextBuildFileMetadata[];
  warnings: string[];
  blocking_reasons: string[];
};

export type ContextBuildCompileResponse = {
  run_id: string;
  status: string;
  bundle_hash: string | null;
  context_version: string | null;
  readiness_status: "ready" | "warning" | "blocked" | "unknown" | string;
  warnings: string[];
  blocking_reasons: string[];
};

type ContextBuildRunApiResponse = {
  id: string;
  status: string;
  bundle_hash: string | null;
  context_version: string | null;
  readiness_status: "ready" | "warning" | "blocked" | string | null;
  warnings: string[];
  errors: string[];
};

export type JobStatus = {
  job_id: string;
  status: string;
  source_id: string;
  started_at: string | null;
  finished_at: string | null;
  error_message: string | null;
  chunks_created: number | null;
};

export type ReviewQueueItem = {
  chunk_id: string;
  source_id: string;
  source_name: string;
  chunk_index: number;
  content_preview: string;
  facts_total: number;
  facts_pending: number;
  rules_total: number;
  rules_pending: number;
  unknown_total: number;
  has_ambiguities: boolean;
  created_at: string;
};

export type EvidenceSpan = {
  id: string;
  quote: string;
  char_start: number | null;
  char_end: number | null;
  page_number: number | null;
  sheet_name: string | null;
  row_number: number | null;
};

export type ExtractedFact = {
  id: string;
  fact_type: string;
  schema_version: string;
  content: Record<string, unknown>;
  normalized_content: Record<string, unknown>;
  status: string;
  confidence: number | null;
  model_name: string | null;
  prompt_version: string | null;
  evidence_span: EvidenceSpan | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  supersedes: string | null;
  superseded_by: string | null;
  created_at: string;
};

export type BusinessRule = {
  id: string;
  rule_type: string;
  schema_version: string;
  condition: Record<string, unknown>;
  action: Record<string, unknown>;
  status: string;
  confidence: number | null;
  model_name: string | null;
  prompt_version: string | null;
  evidence_span: EvidenceSpan | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  supersedes: string | null;
  superseded_by: string | null;
  created_at: string;
};

export type ReviewQueueResponse = {
  items: ReviewQueueItem[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
};

export type ChunkDetail = {
  chunk_id: string;
  source_id: string;
  source_name: string;
  chunk_index: number;
  content: string;
  facts: ExtractedFact[];
  rules: BusinessRule[];
};

export type UnknownQueueItem = {
  id: string;
  chunk_id: string;
  source_id: string;
  raw_text: string;
  suggested_fact_type: string | null;
  confidence: number | null;
  status: string;
  resolution: string | null;
  resolved_by: string | null;
  resolved_at: string | null;
  created_at: string;
};

export type UnknownQueueResponse = {
  items: UnknownQueueItem[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
};

export type PublishedFactRecord = {
  kind: "fact";
  id: string;
  fact_type: string;
  schema_version: string;
  normalized_content: Record<string, unknown>;
  confidence: number | null;
  source_id: string;
  chunk_id: string;
  published_at: string | null;
  reviewed_by: string | null;
};

export type PublishedRuleRecord = {
  kind: "rule";
  id: string;
  rule_type: string;
  schema_version: string;
  condition: Record<string, unknown>;
  action: Record<string, unknown>;
  priority: number;
  confidence: number | null;
  source_id: string;
  chunk_id: string;
  published_at: string | null;
  reviewed_by: string | null;
};

export type KnowledgeRecord = PublishedFactRecord | PublishedRuleRecord;

export type KnowledgeListResponse = {
  items: KnowledgeRecord[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
  facts_count: number;
  rules_count: number;
};

export type QueryResponse = {
  audit_id: string;
  answer_state:
    | "valid_answer"
    | "not_found"
    | "conflicting_sources"
    | "needs_human_validation"
    | "partial_answer";
  answer: string;
  confidence: number;
  used_unvalidated_data: boolean;
  facts_used: string[];
  rules_used: string[];
  sources_used: string[];
  evidence: Array<{
    source_id: string | null;
    source_name: string | null;
    evidence_span_id: string | null;
    quote: string | null;
    page_number: number | null;
    sheet_name: string | null;
    row_number: number | null;
    chunk_id: string | null;
    fact_id: string | null;
    rule_id: string | null;
  }>;
  missing_data: string[];
  warnings: string[];
  usage: {
    model_provider: string | null;
    model_name: string | null;
    model_context_limit_tokens: number | null;
    context_budget_tokens: number;
    context_pack_tokens_estimated: number;
    input_tokens: number;
    output_tokens: number;
    estimated_cost: number;
  };
};

export async function preflightContextBuildRun(
  workspaceId: string,
  token: string,
  request: ContextBuildPreflightRequest
): Promise<ContextBuildPreflightResponse> {
  return apiFetch<ContextBuildPreflightResponse>(
    `/workspaces/${workspaceId}/context-build-runs/preflight`,
    {
      method: "POST",
      token,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...request, persist: request.persist ?? true })
    }
  );
}

export async function stageContextBuildUpload(
  workspaceId: string,
  token: string,
  files: File[]
): Promise<ContextBuildStagedUploadResponse> {
  const formData = new FormData();
  const relativePaths = files.map((file) => file.webkitRelativePath || file.name);

  for (const file of files) {
    formData.append("files", file, file.name);
  }
  formData.append("relative_paths", JSON.stringify(relativePaths));

  return apiFetch<ContextBuildStagedUploadResponse>(
    `/workspaces/${workspaceId}/context-build-runs/staged-uploads`,
    {
      method: "POST",
      token,
      body: formData
    }
  );
}

export async function compileContextBuildRun(
  workspaceId: string,
  token: string,
  runId: string
): Promise<ContextBuildCompileResponse> {
  const response = await apiFetch<ContextBuildRunApiResponse>(
    `/workspaces/${workspaceId}/context-build-runs/${runId}/actions/compile`,
    {
      method: "POST",
      token,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirmation: true })
    }
  );
  return {
    run_id: response.id,
    status: response.status,
    bundle_hash: response.bundle_hash,
    context_version: response.context_version,
    readiness_status: response.readiness_status ?? "unknown",
    warnings: response.warnings,
    blocking_reasons: response.errors
  };
}
