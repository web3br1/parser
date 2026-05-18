"use client";

import type { ReactNode } from "react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  Check,
  Edit3,
  FileQuestion,
  Loader2,
  RefreshCw,
  Send,
  X
} from "lucide-react";
import {
  apiFetch,
  apiMessage,
  type BusinessRule,
  type ChunkDetail,
  type ExtractedFact,
  type ReviewQueueItem,
  type ReviewQueueResponse
} from "@/lib/api";
import { AlertMessage, LoadingState, Pill, StatusBadge } from "@/components/console-primitives";
import { FACT_TYPES } from "@/lib/domain-options";
import { formatConfidence, formatDate, shortId } from "@/lib/format";

type ReviewRecord = ExtractedFact | BusinessRule;
type RecordKind = "fact" | "rule";
type ActionResponse = {
  status: string;
  resource_id: string;
  resource_type: string;
};
type ReviewFilters = {
  factType: string;
  sourceId: string;
};

type ReviewConsoleProps = {
  workspaceId: string;
  token: string;
};

type BusyState = {
  id: string;
  action: string;
} | null;

export function ReviewConsole({ workspaceId, token }: ReviewConsoleProps) {
  const [queue, setQueue] = useState<ReviewQueueItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ChunkDetail | null>(null);
  const [factType, setFactType] = useState("");
  const [sourceId, setSourceId] = useState("");
  const [appliedFilters, setAppliedFilters] = useState<ReviewFilters>({ factType: "", sourceId: "" });
  const [refreshNonce, setRefreshNonce] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<BusyState>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const selected = useMemo(
    () => queue.find((item) => item.chunk_id === selectedId) ?? null,
    [queue, selectedId]
  );

  const progress = useMemo(() => {
    const records = detail ? [...detail.facts, ...detail.rules] : [];
    return {
      total: records.length,
      pending: records.filter((record) => isPending(record.status)).length,
      approved: records.filter((record) => record.status === "approved").length,
      published: records.filter((record) => record.status === "published").length,
      rejected: records.filter((record) => record.status === "rejected").length,
      unknown: selected?.unknown_total ?? 0
    };
  }, [detail, selected?.unknown_total]);

  const loadDetail = useCallback(
    async (chunkId: string) => {
      setError(null);
      setDetail(null);
      try {
        setDetail(
          await apiFetch<ChunkDetail>(`/workspaces/${workspaceId}/review/${chunkId}`, {
            token
          })
        );
      } catch (caught) {
        setError(apiMessage(caught));
      }
    },
    [token, workspaceId]
  );

  const loadQueue = useCallback(
    async (preferredSelectedId?: string | null) => {
      setLoading(true);
      setError(null);
      const params = new URLSearchParams({ per_page: "50" });
      if (appliedFilters.factType) {
        params.set("fact_type", appliedFilters.factType);
      }
      if (appliedFilters.sourceId) {
        params.set("source_id", appliedFilters.sourceId);
      }

      try {
        const response = await apiFetch<ReviewQueueResponse>(
          `/workspaces/${workspaceId}/review?${params.toString()}`,
          { token }
        );
        setQueue(response.items);
        const candidateId = preferredSelectedId ?? null;
        const nextSelectedId = response.items.some((item) => item.chunk_id === candidateId)
          ? candidateId
          : response.items[0]?.chunk_id ?? null;
        setSelectedId(nextSelectedId);
        if (nextSelectedId) {
          await loadDetail(nextSelectedId);
        } else {
          setDetail(null);
        }
      } catch (caught) {
        setError(apiMessage(caught));
      } finally {
        setLoading(false);
      }
    },
    [appliedFilters.factType, appliedFilters.sourceId, loadDetail, token, workspaceId]
  );

  useEffect(() => {
    void loadQueue();
  }, [loadQueue, refreshNonce]);

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSelectedId(null);
    setAppliedFilters({ factType, sourceId: sourceId.trim() });
    setRefreshNonce((value) => value + 1);
  }

  async function runSimpleAction(
    kind: RecordKind,
    record: ReviewRecord,
    action: "approve" | "publish" | "reject" | "unknown"
  ) {
    setBusy({ id: record.id, action });
    setError(null);
    setMessage(null);
    const base = kind === "fact" ? "facts" : "rules";
    const body =
      action === "approve"
        ? { note: "Approved in console" }
        : action === "reject"
        ? { reason: "operator_rejected", note: "Rejected in console" }
        : action === "unknown"
          ? { reason: "send_to_unknown_queue", note: "Marked unknown from review console" }
          : undefined;

    try {
      const result = await apiFetch<ActionResponse>(
        `/workspaces/${workspaceId}/review/${base}/${record.id}/${action === "unknown" ? "reject" : action}`,
        {
          token,
          method: "POST",
          headers: body ? { "Content-Type": "application/json" } : undefined,
          body: body ? JSON.stringify(body) : undefined
        }
      );
      setMessage(actionMessage(action, result));
      await loadQueue(selectedId);
    } catch (caught) {
      setError(apiMessage(caught));
    } finally {
      setBusy(null);
    }
  }

  async function editAndApprove(kind: RecordKind, record: ReviewRecord, value: Record<string, unknown>) {
    setBusy({ id: record.id, action: "edit" });
    setError(null);
    setMessage(null);
    const base = kind === "fact" ? "facts" : "rules";
    const editBody =
      kind === "fact"
        ? { content: value, note: "Edited and approved in console" }
        : {
            condition: asRecord(value.condition),
            action: asRecord(value.action),
            note: "Edited and approved in console"
          };

    try {
      const edited = await apiFetch<ActionResponse>(
        `/workspaces/${workspaceId}/review/${base}/${record.id}/edit`,
        {
          token,
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(editBody)
        }
      );
      await apiFetch<ActionResponse>(
        `/workspaces/${workspaceId}/review/${base}/${edited.resource_id}/approve`,
        {
          token,
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ note: "Approved after edit in console" })
        }
      );
      setMessage(`Edited and approved ${kind} ${shortId(edited.resource_id)}.`);
      await loadQueue(selectedId);
    } catch (caught) {
      setError(apiMessage(caught));
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="mx-auto max-w-7xl text-slate-950">
      <div className="mb-5 flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Review Queue</h1>
          <p className="text-sm text-slate-600">
            Validate extracted facts and rules against the original chunk before publishing.
          </p>
        </div>
        <form onSubmit={applyFilters} className="grid gap-2 md:grid-cols-[190px_minmax(240px,1fr)_auto]">
          <label className="text-xs font-medium uppercase text-slate-500">
            Type
            <select
              value={factType}
              onChange={(event) => setFactType(event.target.value)}
              className="mt-1 h-9 w-full rounded border border-slate-300 bg-white px-2 text-sm font-normal normal-case text-slate-800 outline-none focus:border-slate-950"
            >
              <option value="">All pending</option>
              {FACT_TYPES.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs font-medium uppercase text-slate-500">
            Source id
            <input
              value={sourceId}
              onChange={(event) => setSourceId(event.target.value)}
              placeholder="Optional UUID"
              className="mt-1 h-9 w-full rounded border border-slate-300 bg-white px-2 text-sm font-normal normal-case text-slate-800 outline-none focus:border-slate-950"
            />
          </label>
          <button
            type="submit"
            className="inline-flex h-9 items-center justify-center gap-2 rounded border border-slate-300 bg-white px-3 text-sm hover:bg-slate-50 md:mt-5"
          >
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            Refresh
          </button>
        </form>
      </div>

      {error ? <AlertMessage tone="error">{error}</AlertMessage> : null}
      {message ? <AlertMessage tone="success">{message}</AlertMessage> : null}

      <section className="grid gap-4 xl:grid-cols-[360px_1fr]">
        <ChunkQueue
          items={queue}
          selectedId={selectedId}
          loading={loading}
          onSelect={(chunkId) => {
            setSelectedId(chunkId);
            void loadDetail(chunkId);
          }}
        />

        <div className="space-y-4">
          <ChunkContext detail={detail} selected={selected} progress={progress} />

          {detail ? (
            <div className="grid gap-4 2xl:grid-cols-2">
              <ReviewSection
                title="Facts"
                kind="fact"
                items={detail.facts}
                busy={busy}
                onApprove={(record) => runSimpleAction("fact", record, "approve")}
                onReject={(record) => runSimpleAction("fact", record, "reject")}
                onMarkUnknown={(record) => runSimpleAction("fact", record, "unknown")}
                onPublish={(record) => runSimpleAction("fact", record, "publish")}
                onEditApprove={(record, value) => editAndApprove("fact", record, value)}
              />
              <ReviewSection
                title="Rules"
                kind="rule"
                items={detail.rules}
                busy={busy}
                onApprove={(record) => runSimpleAction("rule", record, "approve")}
                onReject={(record) => runSimpleAction("rule", record, "reject")}
                onMarkUnknown={(record) => runSimpleAction("rule", record, "unknown")}
                onPublish={(record) => runSimpleAction("rule", record, "publish")}
                onEditApprove={(record, value) => editAndApprove("rule", record, value)}
              />
            </div>
          ) : null}
        </div>
      </section>
    </section>
  );
}

function ChunkQueue({
  items,
  selectedId,
  loading,
  onSelect
}: {
  items: ReviewQueueItem[];
  selectedId: string | null;
  loading: boolean;
  onSelect: (chunkId: string) => void;
}) {
  return (
    <div className="overflow-hidden rounded border border-slate-200 bg-white">
      <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-4 py-2">
        <span className="text-xs font-medium uppercase text-slate-500">Chunks</span>
        <span className="text-xs text-slate-500">{items.length} loaded</span>
      </div>
      {loading ? (
        <LoadingState>Loading review queue...</LoadingState>
      ) : items.length === 0 ? (
        <div className="p-4 text-sm text-slate-600">No extracted chunks need review.</div>
      ) : (
        <div className="max-h-[calc(100vh-260px)] overflow-auto">
          {items.map((item) => {
            const pending = item.facts_pending + item.rules_pending;
            return (
              <button
                key={item.chunk_id}
                type="button"
                onClick={() => onSelect(item.chunk_id)}
                className={`block w-full border-b border-slate-100 px-4 py-3 text-left text-sm last:border-b-0 hover:bg-slate-50 ${
                  selectedId === item.chunk_id ? "bg-slate-50" : ""
                }`}
              >
                <span className="block truncate font-medium">{item.source_name || "Untitled source"}</span>
                <span className="mt-1 block line-clamp-2 text-xs leading-5 text-slate-600">
                  {item.content_preview}
                </span>
                <span className="mt-2 flex flex-wrap gap-2 text-xs">
                  <Pill tone={pending > 0 ? "amber" : "slate"}>{pending} pending</Pill>
                  <Pill tone="slate">{item.facts_total} facts</Pill>
                  <Pill tone="slate">{item.rules_total} rules</Pill>
                  {item.unknown_total > 0 ? <Pill tone="violet">{item.unknown_total} unknown</Pill> : null}
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

function ChunkContext({
  detail,
  selected,
  progress
}: {
  detail: ChunkDetail | null;
  selected: ReviewQueueItem | null;
  progress: {
    total: number;
    pending: number;
    approved: number;
    published: number;
    rejected: number;
    unknown: number;
  };
}) {
  return (
    <div className="rounded border border-slate-200 bg-white p-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <h2 className="text-base font-semibold">
            {selected ? selected.source_name || "Selected chunk" : "Chunk detail"}
          </h2>
          <p className="mt-1 text-xs text-slate-500">
            {detail ? `Chunk ${detail.chunk_index} · ${shortId(detail.chunk_id)}` : "Select a chunk to inspect source context."}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Pill tone={progress.pending > 0 ? "amber" : "emerald"}>{progress.pending} pending</Pill>
          <Pill tone="emerald">{progress.approved} approved</Pill>
          <Pill tone="sky">{progress.published} published</Pill>
          <Pill tone="red">{progress.rejected} rejected</Pill>
          <Pill tone="violet">{progress.unknown} unknown</Pill>
        </div>
      </div>
      <pre className="mt-4 max-h-72 overflow-auto whitespace-pre-wrap rounded border border-slate-200 bg-slate-50 p-3 text-sm leading-6 text-slate-800">
        {detail?.content ?? "No chunk selected."}
      </pre>
    </div>
  );
}

function ReviewSection<T extends ReviewRecord>({
  title,
  kind,
  items,
  busy,
  onApprove,
  onReject,
  onMarkUnknown,
  onPublish,
  onEditApprove
}: {
  title: string;
  kind: RecordKind;
  items: T[];
  busy: BusyState;
  onApprove: (record: T) => void;
  onReject: (record: T) => void;
  onMarkUnknown: (record: T) => void;
  onPublish: (record: T) => void;
  onEditApprove: (record: T, value: Record<string, unknown>) => void;
}) {
  return (
    <div className="rounded border border-slate-200 bg-white">
      <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-4 py-2">
        <span className="text-xs font-medium uppercase text-slate-500">{title}</span>
        <span className="text-xs text-slate-500">{items.length}</span>
      </div>
      {items.length === 0 ? (
        <div className="p-4 text-sm text-slate-600">No {title.toLowerCase()} on this chunk.</div>
      ) : (
        <div className="divide-y divide-slate-100">
          {items.map((item) => (
            <ReviewCard
              key={item.id}
              kind={kind}
              item={item}
              busy={busy}
              onApprove={onApprove}
              onReject={onReject}
              onMarkUnknown={onMarkUnknown}
              onPublish={onPublish}
              onEditApprove={onEditApprove}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function ReviewCard<T extends ReviewRecord>({
  kind,
  item,
  busy,
  onApprove,
  onReject,
  onMarkUnknown,
  onPublish,
  onEditApprove
}: {
  kind: RecordKind;
  item: T;
  busy: BusyState;
  onApprove: (record: T) => void;
  onReject: (record: T) => void;
  onMarkUnknown: (record: T) => void;
  onPublish: (record: T) => void;
  onEditApprove: (record: T, value: Record<string, unknown>) => void;
}) {
  const [editing, setEditing] = useState(false);
  const payload = recordPayload(item);
  const payloadText = JSON.stringify(payload, null, 2);
  const [text, setText] = useState(payloadText);
  const [editError, setEditError] = useState<string | null>(null);
  const type = recordType(item);
  const isBusy = busy?.id === item.id;
  const canApprove = isPending(item.status);
  const canPublish = item.status === "approved" || item.status === "published";
  const canEdit = !["published", "deprecated", "superseded", "rejected"].includes(item.status);
  const canReject = !["published", "deprecated", "superseded"].includes(item.status);

  useEffect(() => {
    setText(payloadText);
    setEditError(null);
  }, [item.id, payloadText]);

  function saveEdit() {
    try {
      const parsed = JSON.parse(text) as Record<string, unknown>;
      onEditApprove(item, parsed);
      setEditError(null);
      setEditing(false);
    } catch {
      setEditError("Invalid JSON. Fix the payload before saving.");
    }
  }

  return (
    <article className="p-4">
      <div className="mb-3 flex flex-col gap-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-sm font-semibold">{type}</h3>
              <StatusBadge value={item.status} />
            </div>
            <p className="mt-1 text-xs text-slate-500">
              {kind} · confidence {formatConfidence(item.confidence)} · schema {item.schema_version}
            </p>
          </div>
          {isBusy ? (
            <span className="inline-flex h-8 items-center gap-2 rounded border border-slate-200 px-2.5 text-xs text-slate-600">
              <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
              Working
            </span>
          ) : null}
        </div>

        <div className="flex flex-wrap gap-2">
          <ActionButton icon={<Check className="h-4 w-4" />} label="Approve" disabled={isBusy || !canApprove} onClick={() => onApprove(item)} />
          <ActionButton icon={<Edit3 className="h-4 w-4" />} label={editing ? "Close edit" : "Edit"} disabled={isBusy || !canEdit} onClick={() => setEditing((value) => !value)} />
          <ActionButton icon={<X className="h-4 w-4" />} label="Reject" disabled={isBusy || !canReject} onClick={() => onReject(item)} />
          <ActionButton icon={<FileQuestion className="h-4 w-4" />} label="Mark unknown" disabled={isBusy || !canReject} onClick={() => onMarkUnknown(item)} />
          <ActionButton icon={<Send className="h-4 w-4" />} label="Publish" disabled={isBusy || !canPublish} onClick={() => onPublish(item)} />
        </div>
      </div>

      {editing ? (
        <div>
          <textarea
            value={text}
            onChange={(event) => setText(event.target.value)}
            className="min-h-48 w-full rounded border border-slate-300 p-3 font-mono text-xs outline-none focus:border-slate-950"
          />
          {editError ? <p className="mt-2 text-sm text-red-700">{editError}</p> : null}
          <button
            type="button"
            onClick={saveEdit}
            className="mt-2 inline-flex h-9 items-center rounded bg-slate-950 px-3 text-sm font-medium text-white hover:bg-slate-800"
          >
            Save edit + approve
          </button>
        </div>
      ) : (
        <PayloadView payload={payload} />
      )}

      {item.evidence_span?.quote ? (
        <blockquote className="mt-3 border-l-2 border-slate-300 pl-3 text-sm leading-6 text-slate-700">
          {item.evidence_span.quote}
        </blockquote>
      ) : (
        <p className="mt-3 text-xs text-slate-500">No evidence quote returned for this item.</p>
      )}

      <dl className="mt-3 grid gap-2 text-xs text-slate-500 sm:grid-cols-2">
        <Metadata label="Model" value={item.model_name ?? "n/a"} />
        <Metadata label="Prompt" value={item.prompt_version ?? "n/a"} />
        <Metadata label="Reviewed" value={item.reviewed_at ? formatDate(item.reviewed_at) : "not reviewed"} />
        <Metadata label="Record" value={shortId(item.id)} />
      </dl>
    </article>
  );
}

function PayloadView({ payload }: { payload: Record<string, unknown> }) {
  const entries = Object.entries(payload);
  if (entries.length === 0) {
    return <p className="rounded border border-slate-200 bg-slate-50 p-3 text-sm text-slate-600">No structured payload.</p>;
  }
  return (
    <dl className="grid gap-2 rounded border border-slate-200 bg-slate-50 p-3 text-sm">
      {entries.map(([key, value]) => (
        <div key={key} className="grid gap-1 md:grid-cols-[150px_1fr]">
          <dt className="break-words font-medium text-slate-600">{key}</dt>
          <dd className="min-w-0 break-words text-slate-900">{formatPayloadValue(value)}</dd>
        </div>
      ))}
    </dl>
  );
}

function ActionButton({
  icon,
  label,
  disabled,
  onClick
}: {
  icon: ReactNode;
  label: string;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="inline-flex h-8 items-center gap-1.5 rounded border border-slate-300 bg-white px-2.5 text-xs font-medium hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
    >
      {icon}
      {label}
    </button>
  );
}

function Metadata({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="font-medium text-slate-600">{label}</dt>
      <dd className="mt-0.5 break-all">{value}</dd>
    </div>
  );
}

function isFact(record: ReviewRecord): record is ExtractedFact {
  return "fact_type" in record;
}

function recordType(record: ReviewRecord) {
  return isFact(record) ? record.fact_type : record.rule_type;
}

function recordPayload(record: ReviewRecord): Record<string, unknown> {
  return isFact(record)
    ? record.content
    : {
        condition: record.condition,
        action: record.action
      };
}

function isPending(status: string) {
  return status === "extracted" || status === "needs_review";
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function actionMessage(action: "approve" | "publish" | "reject" | "unknown", result: ActionResponse) {
  if (action === "unknown") {
    return `Marked ${shortId(result.resource_id)} for unknown follow-up.`;
  }
  return `${action[0].toUpperCase()}${action.slice(1)}d ${shortId(result.resource_id)}.`;
}

function formatPayloadValue(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "n/a";
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
}
