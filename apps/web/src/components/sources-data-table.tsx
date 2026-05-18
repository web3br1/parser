import Link from "next/link";
import { FileText } from "lucide-react";
import { StatusBadge } from "@/components/console-primitives";
import type { JobStatus, Source } from "@/lib/api";
import { formatBytes, formatDate } from "@/lib/format";

type SourcesDataTableProps = {
  workspaceId: string;
  sources: Source[];
  jobs: Record<string, JobStatus | "missing">;
  loading: boolean;
};

export function SourcesDataTable({ workspaceId, sources, jobs, loading }: SourcesDataTableProps) {
  return (
    <div className="overflow-hidden rounded border border-slate-200 bg-white">
      <div className="grid min-w-[760px] grid-cols-[minmax(260px,1fr)_130px_130px_170px] border-b border-slate-200 bg-slate-50 px-4 py-2 text-xs font-medium uppercase text-slate-500">
        <span>File</span>
        <span>Source</span>
        <span>Job</span>
        <span>Created</span>
      </div>
      {loading ? (
        <div className="p-6 text-sm text-slate-600">Loading sources...</div>
      ) : sources.length === 0 ? (
        <div className="flex min-h-52 flex-col items-center justify-center p-6 text-center">
          <FileText className="h-8 w-8 text-slate-400" aria-hidden="true" />
          <p className="mt-3 text-sm font-medium text-slate-800">No sources yet</p>
          <p className="mt-1 max-w-sm text-sm text-slate-500">
            Upload the first document to start the ingest and extraction pipeline.
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          {sources.map((source) => (
            <Link
              key={source.id}
              href={`/workspaces/${workspaceId}/sources/${source.id}`}
              className="grid min-w-[760px] grid-cols-[minmax(260px,1fr)_130px_130px_170px] items-center border-b border-slate-100 px-4 py-3 text-sm last:border-b-0"
            >
              <span className="min-w-0">
                <span className="block truncate font-medium text-slate-950">
                  {source.title ?? source.original_filename ?? source.id}
                </span>
                <span className="block truncate text-xs text-slate-500">
                  {source.mime_type ?? "unknown"} / {formatBytes(source.file_size_bytes)}
                </span>
              </span>
              <StatusBadge value={source.status} />
              <StatusBadge value={jobStatus(jobs[source.id])} />
              <span className="text-slate-600">{formatDate(source.created_at)}</span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

function jobStatus(job: JobStatus | "missing" | undefined): string {
  return !job || job === "missing" ? "unknown" : job.status;
}
