"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { RefreshCw } from "lucide-react";
import { FileUploader, type UploadState } from "@/components/file-uploader";
import { SourcesDataTable } from "@/components/sources-data-table";
import { apiFetch, apiMessage, type JobStatus, type Source } from "@/lib/api";
import { useSession } from "@/lib/session";

export default function SourcesPage() {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const { token, ready } = useSession({ required: true });
  const [sources, setSources] = useState<Source[]>([]);
  const [jobs, setJobs] = useState<Record<string, JobStatus | "missing">>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploadState, setUploadState] = useState<UploadState>({ kind: "empty" });

  const loadSources = useCallback(
    async (activeToken: string) => {
      setLoading(true);
      setError(null);
      try {
        const rows = await apiFetch<Source[]>(`/workspaces/${workspaceId}/sources`, {
          token: activeToken
        });
        setSources(rows);
        const settled = await Promise.all(
          rows.slice(0, 12).map(async (source) => {
            try {
              const job = await apiFetch<JobStatus>(
                `/workspaces/${workspaceId}/sources/${source.id}/job`,
                { token: activeToken }
              );
              return [source.id, job] as const;
            } catch {
              return [source.id, "missing"] as const;
            }
          })
        );
        setJobs(Object.fromEntries(settled));
      } catch (caught) {
        setError(apiMessage(caught));
      } finally {
        setLoading(false);
      }
    },
    [workspaceId]
  );

  useEffect(() => {
    if (token) {
      void loadSources(token);
    }
  }, [loadSources, token]);

  if (!ready || !token) {
    return <div className="min-h-96" />;
  }

  return (
    <section className="mx-auto max-w-7xl">
      <div className="mb-5 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <h2 className="text-2xl font-semibold">Sources</h2>
          <p className="text-sm text-slate-600">
            Upload documents and monitor ingest, classification, and extraction status.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void loadSources(token)}
          className="inline-flex h-9 w-fit items-center gap-2 rounded border border-slate-300 bg-white px-3 text-sm hover:bg-slate-50"
        >
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          Refresh
        </button>
      </div>

      {error ? (
        <div className="mb-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          {error}
        </div>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-[360px_1fr]">
        <FileUploader
          workspaceId={workspaceId}
          token={token}
          state={uploadState}
          onStateChange={setUploadState}
          onUploaded={() => loadSources(token)}
        />
        <SourcesDataTable workspaceId={workspaceId} sources={sources} jobs={jobs} loading={loading} />
      </div>
    </section>
  );
}
