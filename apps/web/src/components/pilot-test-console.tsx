"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  BookOpen,
  Database,
  FileSearch,
  Gauge,
  HelpCircle,
  RefreshCw
} from "lucide-react";
import { FileUploader, type UploadState } from "@/components/file-uploader";
import {
  AlertMessage,
  LoadingState,
  Panel,
  PanelHeader,
  StatusBadge
} from "@/components/console-primitives";
import {
  apiFetch,
  apiMessage,
  type JobStatus,
  type KnowledgeListResponse,
  type ReviewQueueResponse,
  type Source,
  type UnknownQueueResponse
} from "@/lib/api";
import {
  buildPilotSteps,
  summarizePilotReadiness,
  type PilotSnapshot,
  type PilotStep
} from "@/lib/pilot-flow";

type PilotTestConsoleProps = {
  workspaceId: string;
  token: string;
};

type PilotData = {
  sources: Source[];
  latestJob: JobStatus | null;
  reviewTotal: number;
  unknownTotal: number;
  knowledgeTotal: number;
};

const emptyData: PilotData = {
  sources: [],
  latestJob: null,
  reviewTotal: 0,
  unknownTotal: 0,
  knowledgeTotal: 0
};

const stepIcons: Record<PilotStep["id"], typeof Gauge> = {
  runtime: Gauge,
  upload: Database,
  pipeline: FileSearch,
  review: BookOpen,
  query: HelpCircle
};

export function PilotTestConsole({ workspaceId, token }: PilotTestConsoleProps) {
  const [data, setData] = useState<PilotData>(emptyData);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploadState, setUploadState] = useState<UploadState>({ kind: "empty" });

  const loadPilotData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [sources, review, unknown, knowledge] = await Promise.all([
        apiFetch<Source[]>(`/workspaces/${workspaceId}/sources`, { token }),
        apiFetch<ReviewQueueResponse>(`/workspaces/${workspaceId}/review?per_page=1`, { token }),
        apiFetch<UnknownQueueResponse>(
          `/workspaces/${workspaceId}/unknown?status=open&per_page=1`,
          { token }
        ),
        apiFetch<KnowledgeListResponse>(`/workspaces/${workspaceId}/knowledge?per_page=1`, {
          token
        })
      ]);

      const latestSource = sources[0] ?? null;
      let latestJob: JobStatus | null = null;
      if (latestSource) {
        try {
          latestJob = await apiFetch<JobStatus>(
            `/workspaces/${workspaceId}/sources/${latestSource.id}/job`,
            { token }
          );
        } catch {
          latestJob = null;
        }
      }

      setData({
        sources,
        latestJob,
        reviewTotal: review.total,
        unknownTotal: unknown.total,
        knowledgeTotal: knowledge.total
      });
    } catch (caught) {
      setError(apiMessage(caught));
      setData(emptyData);
    } finally {
      setLoading(false);
    }
  }, [token, workspaceId]);

  useEffect(() => {
    void loadPilotData();
  }, [loadPilotData]);

  const snapshot = useMemo<PilotSnapshot>(
    () => ({
      apiReachable: !error,
      sourceCount: data.sources.length,
      latestJobStatus: data.latestJob?.status ?? null,
      reviewPending: data.reviewTotal,
      unknownOpen: data.unknownTotal,
      knowledgeTotal: data.knowledgeTotal
    }),
    [data, error]
  );

  const readiness = summarizePilotReadiness(snapshot);
  const steps = buildPilotSteps(snapshot);

  return (
    <section className="mx-auto max-w-7xl">
      <div className="mb-5 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <h2 className="text-2xl font-semibold">Pilot Test</h2>
          <p className="text-sm text-slate-600">
            Validate the local app flow without running smoke scripts.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void loadPilotData()}
          className="inline-flex h-9 w-fit items-center gap-2 rounded border border-slate-300 bg-white px-3 text-sm hover:bg-slate-50"
        >
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          Refresh
        </button>
      </div>

      {error ? <AlertMessage tone="error">{error}</AlertMessage> : null}
      <AlertMessage tone={readiness.tone}>
        <span className="font-medium">{readiness.title}</span>
        <span className="ml-1">{readiness.detail}</span>
      </AlertMessage>

      <div className="grid gap-4 xl:grid-cols-[380px_1fr]">
        <div className="space-y-4">
          <FileUploader
            workspaceId={workspaceId}
            token={token}
            state={uploadState}
            onStateChange={setUploadState}
            onUploaded={loadPilotData}
          />
          <QuickLinks workspaceId={workspaceId} />
        </div>

        <div className="space-y-4">
          <Panel>
            <PanelHeader>Flow status</PanelHeader>
            {loading ? (
              <LoadingState>Loading pilot state...</LoadingState>
            ) : (
              <div className="divide-y divide-slate-200">
                {steps.map((step) => (
                  <PilotStepRow key={step.id} step={step} workspaceId={workspaceId} />
                ))}
              </div>
            )}
          </Panel>

          <Panel>
            <PanelHeader>Workspace snapshot</PanelHeader>
            <div className="grid gap-3 p-4 md:grid-cols-4">
              <Metric label="Sources" value={data.sources.length} />
              <Metric label="Review" value={data.reviewTotal} />
              <Metric label="Unknown" value={data.unknownTotal} />
              <Metric label="Published" value={data.knowledgeTotal} />
            </div>
          </Panel>
        </div>
      </div>
    </section>
  );
}

function PilotStepRow({ step, workspaceId }: { step: PilotStep; workspaceId: string }) {
  const Icon = stepIcons[step.id];
  return (
    <div className="flex flex-col gap-3 px-4 py-4 md:flex-row md:items-center md:justify-between">
      <div className="flex min-w-0 gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded border border-slate-200 bg-slate-50 text-slate-600">
          <Icon className="h-5 w-5" aria-hidden="true" />
        </div>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold text-slate-950">{step.label}</h3>
            <StatusBadge value={step.status} />
          </div>
          <p className="mt-1 text-sm text-slate-600">{step.detail}</p>
        </div>
      </div>
      <StepLink step={step} workspaceId={workspaceId} />
    </div>
  );
}

function StepLink({ step, workspaceId }: { step: PilotStep; workspaceId: string }) {
  const hrefByStep: Partial<Record<PilotStep["id"], string>> = {
    upload: `/workspaces/${workspaceId}/sources`,
    review: `/workspaces/${workspaceId}/review`,
    query: `/workspaces/${workspaceId}/query`
  };
  const href = hrefByStep[step.id];
  if (!href) {
    return null;
  }
  return (
    <Link
      href={href}
      className="inline-flex h-9 w-fit shrink-0 items-center gap-2 rounded border border-slate-300 bg-white px-3 text-sm text-slate-700 hover:bg-slate-50"
    >
      Open
      <ArrowRight className="h-4 w-4" aria-hidden="true" />
    </Link>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded border border-slate-200 bg-slate-50 p-3">
      <div className="text-xs font-medium uppercase text-slate-500">{label}</div>
      <div className="mt-1 text-2xl font-semibold text-slate-950">{value}</div>
    </div>
  );
}

function QuickLinks({ workspaceId }: { workspaceId: string }) {
  return (
    <Panel>
      <PanelHeader>Manual validation</PanelHeader>
      <div className="grid gap-2 p-4 text-sm">
        <Link className="text-slate-700 hover:text-slate-950" href={`/workspaces/${workspaceId}/review`}>
          Review extracted facts and rules
        </Link>
        <Link className="text-slate-700 hover:text-slate-950" href={`/workspaces/${workspaceId}/knowledge`}>
          Inspect published knowledge
        </Link>
        <Link className="text-slate-700 hover:text-slate-950" href={`/workspaces/${workspaceId}/query`}>
          Ask a validation question
        </Link>
      </div>
    </Panel>
  );
}
