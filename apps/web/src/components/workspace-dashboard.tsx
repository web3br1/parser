"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Archive, Database, HelpCircle, Loader2, ShieldQuestion } from "lucide-react";
import {
  apiFetch,
  apiMessage,
  type ReviewQueueResponse,
  type Source,
  type UnknownQueueResponse
} from "@/lib/api";

type WorkspaceDashboardProps = {
  workspaceId: string;
  token: string;
};

export function WorkspaceDashboard({ workspaceId, token }: WorkspaceDashboardProps) {
  const [sources, setSources] = useState<Source[]>([]);
  const [reviewTotal, setReviewTotal] = useState<number | null>(null);
  const [unknownTotal, setUnknownTotal] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [sourceRows, review, unknown] = await Promise.all([
        apiFetch<Source[]>(`/workspaces/${workspaceId}/sources`, { token }),
        apiFetch<ReviewQueueResponse>(`/workspaces/${workspaceId}/review?per_page=1`, { token }),
        apiFetch<UnknownQueueResponse>(`/workspaces/${workspaceId}/unknown?status=open&per_page=1`, { token })
      ]);
      setSources(sourceRows);
      setReviewTotal(review.total);
      setUnknownTotal(unknown.total);
    } catch (caught) {
      setError(apiMessage(caught));
    } finally {
      setLoading(false);
    }
  }, [token, workspaceId]);

  useEffect(() => {
    void load();
  }, [load]);

  const sourceCounts = useMemo(() => {
    return sources.reduce<Record<string, number>>((acc, source) => {
      acc[source.status] = (acc[source.status] ?? 0) + 1;
      return acc;
    }, {});
  }, [sources]);

  return (
    <section className="mx-auto max-w-7xl text-slate-950">
      <div className="mb-5">
        <h1 className="text-2xl font-semibold">Workspace Dashboard</h1>
        <p className="text-sm text-slate-600">Operational snapshot for upload, review, unknown resolution, and query.</p>
      </div>

      {error ? <div className="mb-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</div> : null}

      {loading ? (
        <div className="flex items-center gap-2 rounded border border-slate-200 bg-white p-6 text-sm text-slate-600">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          Loading workspace snapshot...
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <DashboardCard href={`/workspaces/${workspaceId}/sources`} icon={<Database className="h-5 w-5" />} title="Sources" value={String(sources.length)} detail={formatCounts(sourceCounts)} />
          <DashboardCard href={`/workspaces/${workspaceId}/review`} icon={<Archive className="h-5 w-5" />} title="Review Queue" value={String(reviewTotal ?? 0)} detail="chunks awaiting human validation" />
          <DashboardCard href={`/workspaces/${workspaceId}/unknown`} icon={<ShieldQuestion className="h-5 w-5" />} title="Unknown Items" value={String(unknownTotal ?? 0)} detail="open unclassified items" />
          <DashboardCard href={`/workspaces/${workspaceId}/query`} icon={<HelpCircle className="h-5 w-5" />} title="Query" value="Ask" detail="published knowledge only" />
        </div>
      )}
    </section>
  );
}

function DashboardCard({
  href,
  icon,
  title,
  value,
  detail
}: {
  href: string;
  icon: React.ReactNode;
  title: string;
  value: string;
  detail: string;
}) {
  return (
    <Link href={href} className="rounded border border-slate-200 bg-white p-4 hover:bg-slate-50">
      <div className="flex items-center justify-between gap-3 text-slate-600">
        {icon}
        <span className="text-xs font-medium uppercase">{title}</span>
      </div>
      <div className="mt-4 text-3xl font-semibold text-slate-950">{value}</div>
      <p className="mt-2 min-h-10 text-sm leading-5 text-slate-600">{detail}</p>
    </Link>
  );
}

function formatCounts(counts: Record<string, number>) {
  const entries = Object.entries(counts);
  if (entries.length === 0) {
    return "no source rows yet";
  }
  return entries.map(([key, value]) => `${value} ${key}`).join(", ");
}
