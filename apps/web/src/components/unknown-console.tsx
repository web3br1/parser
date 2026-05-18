"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { Ban, Loader2, RefreshCw, RotateCw } from "lucide-react";
import { AlertMessage, LoadingState, Pill, StatusBadge } from "@/components/console-primitives";
import {
  apiFetch,
  apiMessage,
  type ChunkDetail,
  type UnknownQueueItem,
  type UnknownQueueResponse
} from "@/lib/api";
import {
  destinationForFactType,
  MVP_KNOWLEDGE_TYPES,
  normalizeFactType,
  selectableFactType,
  UNKNOWN_STATUS_OPTIONS
} from "@/lib/domain-options";
import { formatConfidence, shortId } from "@/lib/format";

type UnknownConsoleProps = {
  workspaceId: string;
  token: string;
};

type BusyState = {
  id: string;
  action: "reclassify" | "ignore";
} | null;

type ReclassifyResponse = {
  status: string;
  extraction_job_id: string;
};

export function UnknownConsole({ workspaceId, token }: UnknownConsoleProps) {
  const [items, setItems] = useState<UnknownQueueItem[]>([]);
  const [selected, setSelected] = useState<UnknownQueueItem | null>(null);
  const [context, setContext] = useState<ChunkDetail | null>(null);
  const [statusFilter, setStatusFilter] = useState("open");
  const [sourceFilter, setSourceFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [factType, setFactType] = useState<string>(MVP_KNOWLEDGE_TYPES[0]);
  const [note, setNote] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<BusyState>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const visibleItems = useMemo(() => {
    const sourceNeedle = sourceFilter.trim().toLowerCase();
    return items.filter((item) => {
      const matchesSource = sourceNeedle ? item.source_id.toLowerCase().includes(sourceNeedle) : true;
      const matchesType = typeFilter ? item.suggested_fact_type === typeFilter : true;
      return matchesSource && matchesType;
    });
  }, [items, sourceFilter, typeFilter]);

  const counts = useMemo(() => {
    const open = items.filter((item) => item.status === "open").length;
    const mapped = items.filter((item) => item.status === "mapped").length;
    const ignored = items.filter((item) => item.status === "ignored").length;
    return { open, mapped, ignored, total: items.length, visible: visibleItems.length };
  }, [items, visibleItems.length]);

  const loadContext = useCallback(
    async (chunkId: string) => {
      setContext(null);
      try {
        setContext(
          await apiFetch<ChunkDetail>(`/workspaces/${workspaceId}/review/${chunkId}`, {
            token
          })
        );
      } catch {
        setContext(null);
      }
    },
    [token, workspaceId]
  );

  const selectItem = useCallback(
    async (item: UnknownQueueItem | null) => {
      setSelected(item);
      setFactType(selectableFactType(item?.suggested_fact_type));
      setNote("");
      if (item) {
        await loadContext(item.chunk_id);
      } else {
        setContext(null);
      }
    },
    [loadContext]
  );

  const loadUnknowns = useCallback(
    async (preferredSelectedId?: string | null) => {
      setLoading(true);
      setError(null);
      const params = new URLSearchParams({ per_page: "50" });
      if (statusFilter) {
        params.set("status", statusFilter);
      }

      try {
        const response = await apiFetch<UnknownQueueResponse>(
          `/workspaces/${workspaceId}/unknown?${params.toString()}`,
          { token }
        );
        setItems(response.items);
        const candidateId = preferredSelectedId ?? null;
        const nextSelected = response.items.find((item) => item.id === candidateId) ?? response.items[0] ?? null;
        await selectItem(nextSelected);
      } catch (caught) {
        setError(apiMessage(caught));
      } finally {
        setLoading(false);
      }
    },
    [selectItem, statusFilter, token, workspaceId]
  );

  useEffect(() => {
    void loadUnknowns();
  }, [loadUnknowns]);

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void loadUnknowns(selected?.id ?? null);
  }

  async function reclassify(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected || !factType) {
      return;
    }
    const normalizedFactType = normalizeFactType(factType);
    setBusy({ id: selected.id, action: "reclassify" });
    setError(null);
    setMessage(null);
    try {
      const result = await apiFetch<ReclassifyResponse>(
        `/workspaces/${workspaceId}/unknown/${selected.id}/reclassify`,
        {
          token,
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            fact_type: normalizedFactType,
            destination: destinationForFactType(normalizedFactType),
            note: note.trim() || null
          })
        }
      );
      setMessage(`Reclassified ${shortId(selected.id)}. Extraction job ${shortId(result.extraction_job_id)} queued.`);
      await loadUnknowns(null);
    } catch (caught) {
      setError(apiMessage(caught));
    } finally {
      setBusy(null);
    }
  }

  async function ignoreSelected() {
    if (!selected) {
      return;
    }
    setBusy({ id: selected.id, action: "ignore" });
    setError(null);
    setMessage(null);
    try {
      await apiFetch<{ status: string }>(`/workspaces/${workspaceId}/unknown/${selected.id}/ignore`, {
        token,
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ note: note.trim() || "Ignored in console" })
      });
      setMessage(`Ignored ${shortId(selected.id)}.`);
      await loadUnknowns(null);
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
          <h1 className="text-2xl font-semibold">Unknown Queue</h1>
          <p className="text-sm text-slate-600">
            Resolve unclassified chunks by mapping them to an MVP fact or rule type.
          </p>
        </div>
        <form onSubmit={applyFilters} className="grid gap-2 md:grid-cols-[150px_190px_minmax(220px,1fr)_auto]">
          <label className="text-xs font-medium uppercase text-slate-500">
            Status
            <select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
              className="mt-1 h-9 w-full rounded border border-slate-300 bg-white px-2 text-sm font-normal normal-case text-slate-800 outline-none focus:border-slate-950"
            >
              <option value="">All</option>
              {UNKNOWN_STATUS_OPTIONS.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs font-medium uppercase text-slate-500">
            Suggested type
            <select
              value={typeFilter}
              onChange={(event) => setTypeFilter(event.target.value)}
              className="mt-1 h-9 w-full rounded border border-slate-300 bg-white px-2 text-sm font-normal normal-case text-slate-800 outline-none focus:border-slate-950"
            >
              <option value="">All types</option>
              {MVP_KNOWLEDGE_TYPES.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs font-medium uppercase text-slate-500">
            Source id
            <input
              value={sourceFilter}
              onChange={(event) => setSourceFilter(event.target.value)}
              placeholder="Client-side filter"
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
        <UnknownQueue
          items={visibleItems}
          selectedId={selected?.id ?? null}
          counts={counts}
          loading={loading}
          busy={busy}
          onSelect={(item) => void selectItem(item)}
        />

        <div className="space-y-4">
          <ContextPanel selected={selected} context={context} />
          <form onSubmit={reclassify} className="rounded border border-slate-200 bg-white p-4">
            <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
              <div>
                <h2 className="text-base font-semibold">Resolve item</h2>
                <p className="mt-1 text-sm text-slate-600">
                  Reclassification queues a new extraction job; ignore closes the item without publishing knowledge.
                </p>
              </div>
              {selected ? <StatusBadge value={selected.status} /> : null}
            </div>

            <div className="mt-4 grid gap-3 md:grid-cols-2">
              <label className="text-sm font-medium">
                Fact or rule type
                <select
                  value={factType}
                  onChange={(event) => setFactType(event.target.value)}
                  className="mt-1 h-10 w-full rounded border border-slate-300 bg-white px-3 text-sm font-normal outline-none focus:border-slate-950"
                >
                  {MVP_KNOWLEDGE_TYPES.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
              </label>
              <label className="text-sm font-medium">
                Destination
                <select
                  value={destinationForFactType(factType)}
                  disabled
                  className="mt-1 h-10 w-full rounded border border-slate-300 bg-slate-50 px-3 text-sm font-normal text-slate-600 outline-none"
                >
                  <option value="extracted_facts">extracted_facts</option>
                  <option value="business_rules">business_rules</option>
                </select>
              </label>
            </div>

            <label className="mt-3 block text-sm font-medium">
              Operator note
              <textarea
                value={note}
                onChange={(event) => setNote(event.target.value)}
                placeholder="Why this mapping or ignore decision is correct"
                className="mt-1 min-h-24 w-full rounded border border-slate-300 p-3 text-sm font-normal outline-none focus:border-slate-950"
              />
            </label>

            <div className="mt-4 flex flex-wrap gap-2">
              <button
                type="submit"
                disabled={!selected || Boolean(busy) || selected.status !== "open"}
                className="inline-flex h-9 items-center gap-2 rounded bg-slate-950 px-3 text-sm font-medium text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300"
              >
                {busy?.action === "reclassify" ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <RotateCw className="h-4 w-4" aria-hidden="true" />}
                Reclassify
              </button>
              <button
                type="button"
                onClick={() => void ignoreSelected()}
                disabled={!selected || Boolean(busy) || selected.status !== "open"}
                className="inline-flex h-9 items-center gap-2 rounded border border-slate-300 bg-white px-3 text-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {busy?.action === "ignore" ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Ban className="h-4 w-4" aria-hidden="true" />}
                Ignore
              </button>
            </div>
          </form>
        </div>
      </section>
    </section>
  );
}

function UnknownQueue({
  items,
  selectedId,
  counts,
  loading,
  busy,
  onSelect
}: {
  items: UnknownQueueItem[];
  selectedId: string | null;
  counts: { open: number; mapped: number; ignored: number; total: number; visible: number };
  loading: boolean;
  busy: BusyState;
  onSelect: (item: UnknownQueueItem) => void;
}) {
  return (
    <div className="overflow-hidden rounded border border-slate-200 bg-white">
      <div className="border-b border-slate-200 bg-slate-50 px-4 py-3">
        <div className="flex items-center justify-between gap-3">
          <span className="text-xs font-medium uppercase text-slate-500">Unknown items</span>
          <span className="text-xs text-slate-500">{counts.visible}/{counts.total} visible</span>
        </div>
        <div className="mt-2 flex flex-wrap gap-2">
          <Pill tone="amber">{counts.open} open</Pill>
          <Pill tone="emerald">{counts.mapped} mapped</Pill>
          <Pill tone="slate">{counts.ignored} ignored</Pill>
        </div>
      </div>
      {loading ? (
        <LoadingState>Loading unknown queue...</LoadingState>
      ) : items.length === 0 ? (
        <div className="p-4 text-sm text-slate-600">No unknown items match these filters.</div>
      ) : (
        <div className="max-h-[calc(100vh-285px)] overflow-auto">
          {items.map((item) => {
            const isBusy = busy?.id === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => onSelect(item)}
                className={`block w-full border-b border-slate-100 px-4 py-3 text-left text-sm last:border-b-0 hover:bg-slate-50 ${
                  selectedId === item.id ? "bg-slate-50" : ""
                }`}
              >
                <span className="flex items-center justify-between gap-2">
                  <span className="truncate font-medium">{item.suggested_fact_type ?? "unknown"}</span>
                  {isBusy ? <Loader2 className="h-4 w-4 animate-spin text-slate-500" aria-hidden="true" /> : <StatusBadge value={item.status} />}
                </span>
                <span className="mt-1 block line-clamp-3 text-xs leading-5 text-slate-600">{item.raw_text}</span>
                <span className="mt-2 flex flex-wrap gap-2 text-xs text-slate-500">
                  <span>confidence {formatConfidence(item.confidence)}</span>
                  <span>source {shortId(item.source_id)}</span>
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

function ContextPanel({ selected, context }: { selected: UnknownQueueItem | null; context: ChunkDetail | null }) {
  return (
    <div className="rounded border border-slate-200 bg-white p-4">
      <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
        <div>
          <h2 className="text-base font-semibold">Source and chunk context</h2>
          <p className="mt-1 text-xs text-slate-500">
            {selected ? `Unknown ${shortId(selected.id)} · chunk ${shortId(selected.chunk_id)}` : "Select an unknown item."}
          </p>
        </div>
        {context ? <Pill tone="sky">chunk {context.chunk_index}</Pill> : null}
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <div>
          <div className="mb-1 text-xs font-medium uppercase text-slate-500">Unknown text</div>
          <pre className="min-h-52 whitespace-pre-wrap rounded border border-slate-200 bg-slate-50 p-3 text-sm leading-6 text-slate-800">
            {selected?.raw_text ?? "No item selected."}
          </pre>
        </div>
        <div>
          <div className="mb-1 text-xs font-medium uppercase text-slate-500">Full chunk</div>
          <pre className="min-h-52 max-h-96 overflow-auto whitespace-pre-wrap rounded border border-slate-200 bg-slate-50 p-3 text-sm leading-6 text-slate-800">
            {context?.content ?? "Chunk detail is unavailable or requires review access."}
          </pre>
        </div>
      </div>
    </div>
  );
}
