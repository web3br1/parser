"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle, ArrowLeft, Loader2, RefreshCw } from "lucide-react";
import { apiFetch, apiMessage, type JobStatus, type Source } from "@/lib/api";

type SourceDetailProps = {
  workspaceId: string;
  sourceId: string;
  token: string;
};

export function SourceDetail({ workspaceId, sourceId, token }: SourceDetailProps) {
  const [source, setSource] = useState<Source | null>(null);
  const [job, setJob] = useState<JobStatus | "missing" | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const loadedSource = await apiFetch<Source>(`/workspaces/${workspaceId}/sources/${sourceId}`, {
        token
      });
      setSource(loadedSource);
      try {
        setJob(
          await apiFetch<JobStatus>(`/workspaces/${workspaceId}/sources/${sourceId}/job`, {
            token
          })
        );
      } catch {
        setJob("missing");
      }
    } catch (caught) {
      setError(apiMessage(caught));
    } finally {
      setLoading(false);
    }
  }, [sourceId, token, workspaceId]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section className="mx-auto max-w-5xl text-slate-950">
      <div className="mb-5 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <Link href={`/workspaces/${workspaceId}/sources`} className="inline-flex items-center gap-2 text-sm text-slate-600 hover:text-slate-950">
            <ArrowLeft className="h-4 w-4" aria-hidden="true" />
            Sources
          </Link>
          <h1 className="mt-2 text-2xl font-semibold">{source?.title ?? source?.original_filename ?? "Source detail"}</h1>
          <p className="text-sm text-slate-600">Inspect source metadata and latest ingest job state.</p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          className="inline-flex h-9 w-fit items-center gap-2 rounded border border-slate-300 bg-white px-3 text-sm hover:bg-slate-50"
        >
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          Refresh
        </button>
      </div>

      {error ? (
        <div className="mb-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          <div className="flex gap-2">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            <span>{error}</span>
          </div>
        </div>
      ) : null}

      {loading ? (
        <div className="flex items-center gap-2 rounded border border-slate-200 bg-white p-6 text-sm text-slate-600">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          Loading source...
        </div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          <SourcePanel source={source} />
          <JobPanel job={job} />
        </div>
      )}
    </section>
  );
}

function SourcePanel({ source }: { source: Source | null }) {
  return (
    <div className="rounded border border-slate-200 bg-white p-4">
      <h2 className="text-base font-semibold">Source</h2>
      {source ? (
        <dl className="mt-4 space-y-3 text-sm">
          <Metric label="Status" value={source.status} />
          <Metric label="Filename" value={source.original_filename ?? "n/a"} />
          <Metric label="MIME" value={source.mime_type ?? "unknown"} />
          <Metric label="Size" value={formatBytes(source.file_size_bytes)} />
          <Metric label="Created" value={new Date(source.created_at).toLocaleString()} />
          <Metric label="Source id" value={source.id} />
        </dl>
      ) : (
        <p className="mt-2 text-sm text-slate-600">Source not loaded.</p>
      )}
    </div>
  );
}

function JobPanel({ job }: { job: JobStatus | "missing" | null }) {
  return (
    <div className="rounded border border-slate-200 bg-white p-4">
      <h2 className="text-base font-semibold">Latest ingest job</h2>
      {!job ? (
        <p className="mt-2 text-sm text-slate-600">Job not loaded.</p>
      ) : job === "missing" ? (
        <p className="mt-2 text-sm text-slate-600">No ingest job found for this source.</p>
      ) : (
        <dl className="mt-4 space-y-3 text-sm">
          <Metric label="Status" value={job.status} />
          <Metric label="Chunks created" value={job.chunks_created === null ? "n/a" : String(job.chunks_created)} />
          <Metric label="Started" value={job.started_at ? new Date(job.started_at).toLocaleString() : "not started"} />
          <Metric label="Finished" value={job.finished_at ? new Date(job.finished_at).toLocaleString() : "not finished"} />
          <Metric label="Error" value={job.error_message ?? "none"} />
          <Metric label="Job id" value={job.job_id} />
        </dl>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid gap-1 sm:grid-cols-[140px_1fr]">
      <dt className="font-medium text-slate-600">{label}</dt>
      <dd className="break-all text-slate-950">{value}</dd>
    </div>
  );
}

function formatBytes(value: number | null) {
  if (!value) {
    return "size unknown";
  }
  if (value < 1024 * 1024) {
    return `${Math.max(1, Math.round(value / 1024))} KB`;
  }
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}
