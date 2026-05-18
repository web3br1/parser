"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ChevronDown, ChevronUp, RefreshCw } from "lucide-react";
import {
  apiFetch,
  apiMessage,
  type KnowledgeListResponse,
  type KnowledgeRecord,
} from "@/lib/api";
import {
  AlertMessage,
  EmptyState,
  LoadingState,
  Panel,
  PanelHeader,
  Pill,
} from "@/components/console-primitives";
import { MVP_KNOWLEDGE_TYPES } from "@/lib/domain-options";
import { formatConfidence, formatDate, shortId } from "@/lib/format";

type KnowledgeConsoleProps = {
  workspaceId: string;
  token: string;
};

type Filters = {
  recordType: string;
  kindFilter: string;
  sourceId: string;
};

const PER_PAGE = 20;

export function KnowledgeConsole({ workspaceId, token }: KnowledgeConsoleProps) {
  const [data, setData] = useState<KnowledgeListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [committed, setCommitted] = useState<Filters>({
    recordType: "all",
    kindFilter: "",
    sourceId: "",
  });
  const [draftKindFilter, setDraftKindFilter] = useState("");
  const [draftSourceId, setDraftSourceId] = useState("");

  const [page, setPage] = useState(1);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const load = useCallback(
    async (filters: Filters, p: number) => {
      setLoading(true);
      setError(null);
      try {
        const params = new URLSearchParams({
          record_type: filters.recordType,
          page: String(p),
          per_page: String(PER_PAGE),
        });
        if (filters.kindFilter) params.set("kind_filter", filters.kindFilter);
        if (filters.sourceId.trim()) params.set("source_id", filters.sourceId.trim());
        const result = await apiFetch<KnowledgeListResponse>(
          `/workspaces/${workspaceId}/knowledge?${params}`,
          { token }
        );
        setData(result);
      } catch (err) {
        setError(apiMessage(err));
      } finally {
        setLoading(false);
      }
    },
    [workspaceId, token]
  );

  useEffect(() => {
    load(committed, page);
  }, [load, committed, page]);

  function applyFilters() {
    setCommitted((prev) => ({ ...prev, kindFilter: draftKindFilter, sourceId: draftSourceId }));
    setPage(1);
  }

  function setRecordType(rt: string) {
    setCommitted((prev) => ({ ...prev, recordType: rt }));
    setPage(1);
  }

  function toggleExpand(id: string) {
    setExpandedId((prev) => (prev === id ? null : id));
  }

  return (
    <section className="mx-auto max-w-5xl text-slate-950">
      <div className="mb-5 flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Knowledge Base</h1>
          <p className="text-sm text-slate-600">
            Read-only browser of approved, published facts and rules.
          </p>
        </div>
        <button
          onClick={() => load(committed, page)}
          className="inline-flex h-8 items-center gap-1.5 rounded border border-slate-300 bg-white px-3 text-sm hover:bg-slate-50"
        >
          <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
          Refresh
        </button>
      </div>

      {/* Filter bar */}
      <div className="mb-4 flex flex-wrap items-end gap-3 rounded border border-slate-200 bg-white p-3">
        <div>
          <p className="mb-1 text-xs font-medium text-slate-500">Record type</p>
          <div className="flex overflow-hidden rounded border border-slate-200 text-sm">
            {(["all", "facts", "rules"] as const).map((rt) => (
              <button
                key={rt}
                onClick={() => setRecordType(rt)}
                className={`px-3 py-1.5 capitalize ${
                  committed.recordType === rt
                    ? "bg-slate-950 text-white"
                    : "bg-white text-slate-700 hover:bg-slate-50"
                }`}
              >
                {rt}
              </button>
            ))}
          </div>
        </div>

        <div>
          <p className="mb-1 text-xs font-medium text-slate-500">Fact / rule type</p>
          <select
            value={draftKindFilter}
            onChange={(e) => setDraftKindFilter(e.target.value)}
            className="h-9 rounded border border-slate-300 bg-white px-2 text-sm"
          >
            <option value="">All types</option>
            {MVP_KNOWLEDGE_TYPES.map((t) => (
              <option key={t} value={t}>
                {t.replaceAll("_", " ")}
              </option>
            ))}
          </select>
        </div>

        <div>
          <p className="mb-1 text-xs font-medium text-slate-500">Source ID</p>
          <input
            type="text"
            value={draftSourceId}
            onChange={(e) => setDraftSourceId(e.target.value)}
            placeholder="Paste source UUID…"
            className="h-9 w-56 rounded border border-slate-300 bg-white px-2 text-sm placeholder-slate-400"
          />
        </div>

        <button
          onClick={applyFilters}
          className="inline-flex h-9 items-center rounded bg-slate-950 px-3 text-sm font-medium text-white hover:bg-slate-800"
        >
          Apply
        </button>
      </div>

      {/* Summary chips */}
      {data && !loading && (
        <div className="mb-4 flex items-center gap-2 text-sm text-slate-600">
          <Pill tone="emerald">{data.facts_count} facts</Pill>
          <Pill tone="violet">{data.rules_count} rules</Pill>
          <span className="text-slate-400">·</span>
          <span>{data.total} total</span>
        </div>
      )}

      {error && <AlertMessage tone="error">{error}</AlertMessage>}

      {loading && <LoadingState>Loading published records…</LoadingState>}

      {!loading && !error && data && (
        <>
          {data.items.length === 0 ? (
            <Panel>
              <EmptyState>
                No published records yet.{" "}
                <Link
                  href={`/workspaces/${workspaceId}/review`}
                  className="underline"
                >
                  Review queue
                </Link>{" "}
                is where you approve and publish extracted knowledge.
              </EmptyState>
            </Panel>
          ) : (
            <Panel>
              <PanelHeader>
                Published records — page {data.page} of {data.pages}
              </PanelHeader>
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-100 text-left text-xs text-slate-500">
                    <th className="px-4 py-2 font-medium">Kind</th>
                    <th className="px-4 py-2 font-medium">Type</th>
                    <th className="px-4 py-2 font-medium">Preview</th>
                    <th className="px-4 py-2 font-medium">Confidence</th>
                    <th className="px-4 py-2 font-medium">Published</th>
                    <th className="w-8 px-4 py-2 font-medium" />
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((record) => (
                    <KnowledgeRow
                      key={record.id}
                      record={record}
                      expanded={expandedId === record.id}
                      onToggle={() => toggleExpand(record.id)}
                    />
                  ))}
                </tbody>
              </table>
            </Panel>
          )}

          {data.pages > 1 && (
            <div className="mt-4 flex items-center justify-between text-sm">
              <button
                disabled={data.page <= 1}
                onClick={() => setPage((p) => p - 1)}
                className="inline-flex h-8 items-center rounded border border-slate-300 bg-white px-3 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Previous
              </button>
              <span className="text-slate-500">
                Page {data.page} of {data.pages}
              </span>
              <button
                disabled={data.page >= data.pages}
                onClick={() => setPage((p) => p + 1)}
                className="inline-flex h-8 items-center rounded border border-slate-300 bg-white px-3 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
    </section>
  );
}

function KnowledgeRow({
  record,
  expanded,
  onToggle,
}: {
  record: KnowledgeRecord;
  expanded: boolean;
  onToggle: () => void;
}) {
  const type = record.kind === "fact" ? record.fact_type : record.rule_type;
  const preview = contentPreview(record);

  return (
    <>
      <tr
        className={`cursor-pointer border-b border-slate-100 hover:bg-slate-50 ${expanded ? "bg-slate-50" : ""}`}
        onClick={onToggle}
      >
        <td className="px-4 py-2.5">
          <Pill tone={record.kind === "fact" ? "emerald" : "violet"}>{record.kind}</Pill>
        </td>
        <td className="px-4 py-2.5 font-mono text-xs">{type.replaceAll("_", " ")}</td>
        <td className="max-w-xs truncate px-4 py-2.5 text-slate-600">{preview}</td>
        <td className="px-4 py-2.5 text-slate-600">{formatConfidence(record.confidence)}</td>
        <td className="whitespace-nowrap px-4 py-2.5 text-slate-500">
          {formatDate(record.published_at)}
        </td>
        <td className="px-4 py-2.5 text-slate-400">
          {expanded ? (
            <ChevronUp className="h-4 w-4" aria-hidden="true" />
          ) : (
            <ChevronDown className="h-4 w-4" aria-hidden="true" />
          )}
        </td>
      </tr>
      {expanded && (
        <tr className="border-b border-slate-100 bg-slate-50">
          <td colSpan={6} className="px-4 pb-4 pt-2">
            <ExpandedContent record={record} />
          </td>
        </tr>
      )}
    </>
  );
}

function ExpandedContent({ record }: { record: KnowledgeRecord }) {
  if (record.kind === "fact") {
    return (
      <div className="space-y-2">
        <p className="text-xs font-medium text-slate-500">Normalized content</p>
        <pre className="overflow-auto rounded bg-slate-100 p-3 text-xs text-slate-800">
          {JSON.stringify(record.normalized_content, null, 2)}
        </pre>
        <div className="flex flex-wrap gap-4 text-xs text-slate-500">
          <span>
            Source: <span className="font-mono">{shortId(record.source_id)}</span>
          </span>
          <span>
            Chunk: <span className="font-mono">{shortId(record.chunk_id)}</span>
          </span>
          <span>Schema: {record.schema_version}</span>
          {record.reviewed_by && (
            <span>
              Reviewed by: <span className="font-mono">{shortId(record.reviewed_by)}</span>
            </span>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <p className="mb-1 text-xs font-medium text-slate-500">Condition</p>
          <pre className="overflow-auto rounded bg-slate-100 p-3 text-xs text-slate-800">
            {JSON.stringify(record.condition, null, 2)}
          </pre>
        </div>
        <div>
          <p className="mb-1 text-xs font-medium text-slate-500">Action</p>
          <pre className="overflow-auto rounded bg-slate-100 p-3 text-xs text-slate-800">
            {JSON.stringify(record.action, null, 2)}
          </pre>
        </div>
      </div>
      <div className="flex flex-wrap gap-4 text-xs text-slate-500">
        <span>
          Source: <span className="font-mono">{shortId(record.source_id)}</span>
        </span>
        <span>
          Chunk: <span className="font-mono">{shortId(record.chunk_id)}</span>
        </span>
        <span>Priority: {record.priority}</span>
        <span>Schema: {record.schema_version}</span>
        {record.reviewed_by && (
          <span>
            Reviewed by: <span className="font-mono">{shortId(record.reviewed_by)}</span>
          </span>
        )}
      </div>
    </div>
  );
}

function contentPreview(record: KnowledgeRecord): string {
  const content =
    record.kind === "fact" ? record.normalized_content : record.condition;
  return Object.entries(content)
    .slice(0, 2)
    .map(([k, v]) => `${k}: ${String(v)}`)
    .join(" · ");
}
