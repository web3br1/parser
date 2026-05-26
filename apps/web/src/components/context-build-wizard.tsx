"use client";

import { useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  FileSearch,
  FolderOpen,
  Loader2,
  PackageCheck,
  Play,
  Upload
} from "lucide-react";
import {
  AlertMessage,
  Panel,
  PanelHeader,
  StatusBadge
} from "@/components/console-primitives";
import {
  apiMessage,
  compileContextBuildRun,
  preflightContextBuildRun,
  type ContextBuildCompileResponse,
  type ContextBuildFileMetadata,
  type ContextBuildPreflightResponse
} from "@/lib/api";
import {
  detectContextBuildPreview,
  type ContextBuildPreview,
  type ContextBuildPreviewFile
} from "@/lib/context-build";

type ContextBuildWizardProps = {
  workspaceId: string;
  token: string;
};

type BusyAction = "preflight" | "compile" | null;

const steps = [
  "Select input",
  "Detect",
  "Preflight",
  "Build",
  "Review/Publish",
  "Generate Bundle",
  "Ready/Warning/Blocked"
];

export function ContextBuildWizard({ workspaceId, token }: ContextBuildWizardProps) {
  const [files, setFiles] = useState<File[]>([]);
  const [preflight, setPreflight] = useState<ContextBuildPreflightResponse | null>(null);
  const [compileResult, setCompileResult] = useState<ContextBuildCompileResponse | null>(null);
  const [busyAction, setBusyAction] = useState<BusyAction>(null);
  const [error, setError] = useState<string | null>(null);

  const previewFiles = useMemo(() => files.map(toPreviewFile), [files]);
  const metadata = useMemo(() => files.map(toFileMetadata), [files]);
  const preview = useMemo(() => detectContextBuildPreview(previewFiles), [previewFiles]);
  const fingerprint = useMemo(() => buildInputFingerprint(metadata), [metadata]);

  const canPreflight = files.length > 0 && busyAction === null;
  const canCompile =
    preflight?.run_id &&
    preflight.recommended_action === "compile_as_source_pack" &&
    preflight.blocking_reasons.length === 0 &&
    busyAction === null;

  async function handlePreflight() {
    if (!canPreflight) {
      return;
    }
    setBusyAction("preflight");
    setError(null);
    setCompileResult(null);
    try {
      const result = await preflightContextBuildRun(workspaceId, token, {
        files: metadata,
        input_fingerprint: fingerprint
      });
      setPreflight(result);
    } catch (caught) {
      setError(apiMessage(caught));
    } finally {
      setBusyAction(null);
    }
  }

  async function handleCompile() {
    if (!canCompile || !preflight?.run_id) {
      return;
    }
    setBusyAction("compile");
    setError(null);
    try {
      const result = await compileContextBuildRun(workspaceId, token, preflight.run_id);
      setCompileResult(result);
    } catch (caught) {
      setError(apiMessage(caught));
    } finally {
      setBusyAction(null);
    }
  }

  return (
    <section className="mx-auto max-w-7xl">
      <div className="mb-5 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <h2 className="text-2xl font-semibold">Context Build</h2>
          <p className="text-sm text-slate-600">
            Compile source documents into an auditable context bundle.
          </p>
        </div>
        <StatusBadge value={currentStatus(preview, preflight, compileResult)} />
      </div>

      {error ? <AlertMessage tone="error">{error}</AlertMessage> : null}
      <ReadinessNotice preflight={preflight} compileResult={compileResult} />

      <div className="grid gap-4 xl:grid-cols-[380px_1fr]">
        <div className="space-y-4">
          <Panel>
            <PanelHeader>Select input</PanelHeader>
            <div className="space-y-4 p-4">
              <label className="flex min-h-40 cursor-pointer flex-col items-center justify-center rounded border border-dashed border-slate-300 bg-slate-50 px-4 py-6 text-center hover:bg-slate-100">
                <FolderOpen className="h-8 w-8 text-slate-500" aria-hidden="true" />
                <span className="mt-3 text-sm font-medium text-slate-950">
                  Select documents or a full source pack folder
                </span>
                <span className="mt-1 text-xs text-slate-500">
                  This preflight sends file metadata first; backend staging comes next.
                </span>
                <input
                  className="sr-only"
                  type="file"
                  multiple
                  onChange={(event) => {
                    setFiles(Array.from(event.target.files ?? []));
                    setPreflight(null);
                    setCompileResult(null);
                    setError(null);
                  }}
                />
              </label>

              <label className="flex cursor-pointer items-center justify-center gap-2 rounded border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50">
                <FolderOpen className="h-4 w-4" aria-hidden="true" />
                Select Folder
                <input
                  className="sr-only"
                  type="file"
                  multiple
                  onChange={(event) => {
                    setFiles(Array.from(event.target.files ?? []));
                    setPreflight(null);
                    setCompileResult(null);
                    setError(null);
                  }}
                  {...folderInputAttributes}
                />
              </label>

              <div className="grid grid-cols-3 gap-2">
                <Metric label="Files" value={preview.fileCount} />
                <Metric label="Supported" value={preview.supportedFileCount} />
                <Metric label="Blocked" value={preview.blockedFiles.length} />
              </div>

              <button
                type="button"
                onClick={() => void handlePreflight()}
                disabled={!canPreflight}
                className="inline-flex h-9 w-full items-center justify-center gap-2 rounded bg-slate-950 px-3 text-sm font-medium text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300"
              >
                {busyAction === "preflight" ? (
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                ) : (
                  <Upload className="h-4 w-4" aria-hidden="true" />
                )}
                Preflight Selection
              </button>
            </div>
          </Panel>

          <Panel>
            <PanelHeader>Detected extensions</PanelHeader>
            <ExtensionList preview={preview} />
          </Panel>
        </div>

        <div className="space-y-4">
          <Panel>
            <PanelHeader>Build flow</PanelHeader>
            <div className="divide-y divide-slate-200">
              {steps.map((label, index) => (
                <StepRow
                  key={label}
                  index={index + 1}
                  label={label}
                  status={stepStatus(index, preview, preflight, compileResult)}
                />
              ))}
            </div>
          </Panel>

          <Panel>
            <PanelHeader>Detection result</PanelHeader>
            <div className="grid gap-4 p-4 lg:grid-cols-2">
              <DetectionCard title="Frontend preview" status={preview.mode}>
                <Detail label="Manifest" value={preview.hasSourceManifest ? "found" : "not found"} />
                <Detail label="Input fingerprint" value={fingerprint || "waiting for files"} />
              </DetectionCard>
              <DetectionCard title="Backend preflight" status={preflight?.input_mode ?? "not_run"}>
                <Detail label="Recommended action" value={preflight?.recommended_action ?? "not available"} />
                <Detail label="Run ID" value={preflight?.run_id ?? "not persisted yet"} />
              </DetectionCard>
            </div>
          </Panel>

          <Panel>
            <PanelHeader>Build actions</PanelHeader>
            <div className="space-y-4 p-4">
              <button
                type="button"
                onClick={() => void handleCompile()}
                disabled={!canCompile}
                className="inline-flex h-9 w-fit items-center gap-2 rounded border border-slate-300 bg-white px-3 text-sm text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-45"
              >
                {busyAction === "compile" ? (
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                ) : (
                  <Play className="h-4 w-4" aria-hidden="true" />
                )}
                Generate Bundle
              </button>

              {compileResult ? (
                <div className="rounded border border-slate-200 bg-slate-50 p-3 text-sm">
                  <div className="mb-2 flex flex-wrap items-center gap-2">
                    <PackageCheck className="h-4 w-4 text-slate-600" aria-hidden="true" />
                    <StatusBadge value={compileResult.status} />
                    <StatusBadge value={compileResult.readiness_status} />
                  </div>
                  <Detail label="Context version" value={compileResult.context_version ?? "not emitted"} />
                  <Detail label="Bundle hash" value={compileResult.bundle_hash ?? "not emitted"} />
                </div>
              ) : (
                <p className="text-sm text-slate-600">
                  Run preflight first. Source packs can be compiled only after the backend has staged content.
                </p>
              )}
            </div>
          </Panel>

          <IssuesPanel preflight={preflight} compileResult={compileResult} preview={preview} />
        </div>
      </div>
    </section>
  );
}

const folderInputAttributes = {
  directory: "",
  webkitdirectory: ""
} as Record<string, string>;

function toPreviewFile(file: File): ContextBuildPreviewFile {
  return {
    name: file.name,
    size: file.size,
    relativePath: file.webkitRelativePath || file.name,
    type: file.type || undefined,
    lastModified: file.lastModified
  };
}

function toFileMetadata(file: File): ContextBuildFileMetadata {
  return {
    name: file.name,
    size: file.size,
    relative_path: file.webkitRelativePath || null,
    mime_type: file.type || null,
    last_modified: file.lastModified || null
  };
}

function buildInputFingerprint(files: ContextBuildFileMetadata[]): string {
  if (files.length === 0) {
    return "";
  }
  return files
    .map((file) => `${file.relative_path ?? file.name}:${file.size}:${file.last_modified ?? 0}`)
    .sort()
    .join("|");
}

function currentStatus(
  preview: ContextBuildPreview,
  preflight: ContextBuildPreflightResponse | null,
  compileResult: ContextBuildCompileResponse | null
): string {
  if (compileResult) {
    return compileResult.readiness_status;
  }
  if (preflight) {
    return preflight.status;
  }
  return preview.mode;
}

function stepStatus(
  index: number,
  preview: ContextBuildPreview,
  preflight: ContextBuildPreflightResponse | null,
  compileResult: ContextBuildCompileResponse | null
): "completed" | "current" | "blocked" | "pending" {
  if (index === 0) {
    return preview.fileCount > 0 ? "completed" : "current";
  }
  if (index === 1) {
    if (preflight) {
      return "completed";
    }
    if (preview.mode === "invalid_preview") {
      return preview.fileCount > 0 ? "blocked" : "pending";
    }
    return preview.fileCount > 0 ? "completed" : "pending";
  }
  if (index === 2) {
    return preflight ? "completed" : preview.fileCount > 0 ? "current" : "pending";
  }
  if (index === 3 || index === 4) {
    if (!preflight) {
      return "pending";
    }
    return "current";
  }
  if (index === 5) {
    if (compileResult) {
      return "completed";
    }
    return preflight?.recommended_action === "compile_as_source_pack" ? "current" : "pending";
  }
  if (compileResult) {
    return compileResult.readiness_status === "blocked" ? "blocked" : "completed";
  }
  return "pending";
}

function ReadinessNotice({
  preflight,
  compileResult
}: {
  preflight: ContextBuildPreflightResponse | null;
  compileResult: ContextBuildCompileResponse | null;
}) {
  const warnings = compileResult?.warnings ?? preflight?.warnings ?? [];
  const blockingReasons = compileResult?.blocking_reasons ?? preflight?.blocking_reasons ?? [];

  if (blockingReasons.length > 0) {
    return <AlertMessage tone="error">{blockingReasons[0]}</AlertMessage>;
  }
  if (warnings.length > 0) {
    return <AlertMessage tone="warning">{warnings[0]}</AlertMessage>;
  }
  if (compileResult) {
    return <AlertMessage tone="success">Context bundle generated and ready for import.</AlertMessage>;
  }
  return <AlertMessage tone="info">Backend preflight is authoritative; frontend detection is only a preview.</AlertMessage>;
}

function StepRow({
  index,
  label,
  status
}: {
  index: number;
  label: string;
  status: "completed" | "current" | "blocked" | "pending";
}) {
  return (
    <div className="flex items-center justify-between gap-3 px-4 py-3">
      <div className="flex min-w-0 items-center gap-3">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded border border-slate-200 bg-slate-50 text-xs font-semibold text-slate-600">
          {status === "completed" ? (
            <CheckCircle2 className="h-4 w-4 text-emerald-600" aria-hidden="true" />
          ) : status === "blocked" ? (
            <AlertTriangle className="h-4 w-4 text-red-600" aria-hidden="true" />
          ) : (
            index
          )}
        </div>
        <span className="truncate text-sm font-medium text-slate-950">{label}</span>
      </div>
      <StatusBadge value={status} />
    </div>
  );
}

function DetectionCard({
  title,
  status,
  children
}: {
  title: string;
  status: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded border border-slate-200 bg-slate-50 p-3">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-sm font-semibold text-slate-950">
          <FileSearch className="h-4 w-4 text-slate-500" aria-hidden="true" />
          {title}
        </div>
        <StatusBadge value={status} />
      </div>
      <div className="space-y-2">{children}</div>
    </div>
  );
}

function ExtensionList({ preview }: { preview: ContextBuildPreview }) {
  const entries = Object.entries(preview.extensionCounts).sort(([left], [right]) => left.localeCompare(right));

  if (entries.length === 0) {
    return <div className="p-4 text-sm text-slate-600">No files selected yet.</div>;
  }

  return (
    <div className="divide-y divide-slate-200">
      {entries.map(([extension, count]) => (
        <div key={extension || "none"} className="flex items-center justify-between px-4 py-3 text-sm">
          <span className="font-medium text-slate-700">.{extension || "none"}</span>
          <span className="text-slate-500">{count}</span>
        </div>
      ))}
    </div>
  );
}

function IssuesPanel({
  preflight,
  compileResult,
  preview
}: {
  preflight: ContextBuildPreflightResponse | null;
  compileResult: ContextBuildCompileResponse | null;
  preview: ContextBuildPreview;
}) {
  const warnings = compileResult?.warnings ?? preflight?.warnings ?? [];
  const blockingReasons = compileResult?.blocking_reasons ?? preflight?.blocking_reasons ?? preview.blockedFiles;

  return (
    <Panel>
      <PanelHeader>Warnings and blockers</PanelHeader>
      <div className="space-y-3 p-4">
        {blockingReasons.length === 0 && warnings.length === 0 ? (
          <p className="text-sm text-slate-600">No warnings or blockers reported yet.</p>
        ) : null}
        {blockingReasons.map((reason) => (
          <IssueRow key={`blocker-${reason}`} tone="blocked" text={reason} />
        ))}
        {warnings.map((warning) => (
          <IssueRow key={`warning-${warning}`} tone="warning" text={warning} />
        ))}
      </div>
    </Panel>
  );
}

function IssueRow({ tone, text }: { tone: "blocked" | "warning"; text: string }) {
  return (
    <div className="flex items-start gap-2 rounded border border-slate-200 bg-slate-50 p-3 text-sm">
      <StatusBadge value={tone} />
      <span className="min-w-0 text-slate-700">{text}</span>
    </div>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 text-sm">
      <span className="text-slate-500">{label}: </span>
      <span className="break-all font-medium text-slate-800">{value}</span>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded border border-slate-200 bg-white p-3">
      <div className="text-xs font-medium uppercase text-slate-500">{label}</div>
      <div className="mt-1 text-xl font-semibold text-slate-950">{value}</div>
    </div>
  );
}
