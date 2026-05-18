"use client";

import type { ChangeEvent, DragEvent } from "react";
import { AlertTriangle, CheckCircle2, FileUp, Loader2, UploadCloud } from "lucide-react";
import { apiFetch, apiMessage, type UploadResponse } from "@/lib/api";

type UploadState =
  | { kind: "empty" }
  | { kind: "ready"; file: File }
  | { kind: "uploading"; file: File }
  | { kind: "accepted"; response: UploadResponse }
  | { kind: "duplicate"; message: string }
  | { kind: "rejected"; message: string }
  | { kind: "failed"; message: string };

type FileUploaderProps = {
  workspaceId: string;
  token: string;
  state: UploadState;
  onStateChange: (state: UploadState) => void;
  onUploaded: () => Promise<void>;
};

export function FileUploader({
  workspaceId,
  token,
  state,
  onStateChange,
  onUploaded
}: FileUploaderProps) {
  function pickFile(file: File | undefined) {
    if (file) {
      onStateChange({ kind: "ready", file });
    }
  }

  function onDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    pickFile(event.dataTransfer.files.item(0) ?? undefined);
  }

  async function upload() {
    if (state.kind !== "ready") {
      return;
    }
    const file = state.file;
    onStateChange({ kind: "uploading", file });
    const body = new FormData();
    body.append("file", file);

    try {
      const response = await apiFetch<UploadResponse>(`/workspaces/${workspaceId}/sources/upload`, {
        token,
        method: "POST",
        body
      });
      onStateChange({ kind: "accepted", response });
      await onUploaded();
    } catch (caught) {
      const message = apiMessage(caught);
      if (message.toLowerCase().includes("duplicate")) {
        onStateChange({ kind: "duplicate", message });
      } else if (message.toLowerCase().includes("validation")) {
        onStateChange({ kind: "rejected", message });
      } else {
        onStateChange({ kind: "failed", message });
      }
    }
  }

  return (
    <div className="rounded border border-slate-200 bg-white p-4">
      <label
        onDragOver={(event) => event.preventDefault()}
        onDrop={onDrop}
        className="flex min-h-44 cursor-pointer flex-col items-center justify-center rounded border border-dashed border-slate-300 bg-slate-50 px-4 text-center hover:bg-slate-100"
      >
        <UploadCloud className="mb-3 h-8 w-8 text-slate-500" aria-hidden="true" />
        <span className="text-sm font-medium">Drop a document or choose a file</span>
        <span className="mt-1 text-xs text-slate-500">PDF, DOCX, CSV, XLSX, TXT</span>
        <input
          type="file"
          accept=".pdf,.docx,.csv,.xlsx,.txt"
          className="sr-only"
          onChange={(event: ChangeEvent<HTMLInputElement>) =>
            pickFile(event.target.files?.item(0) ?? undefined)
          }
        />
      </label>

      <UploadStatus state={state} />

      <button
        type="button"
        onClick={() => void upload()}
        disabled={state.kind !== "ready"}
        className="mt-4 inline-flex h-10 w-full items-center justify-center gap-2 rounded bg-slate-950 px-4 text-sm font-medium text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300"
      >
        {state.kind === "uploading" ? (
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
        ) : (
          <FileUp className="h-4 w-4" aria-hidden="true" />
        )}
        Upload source
      </button>
    </div>
  );
}

export type { UploadState };

function UploadStatus({ state }: { state: UploadState }) {
  if (state.kind === "empty") {
    return <p className="mt-3 text-sm text-slate-600">Idle. Select a file to prepare an upload.</p>;
  }
  if (state.kind === "ready") {
    return <p className="mt-3 text-sm text-slate-700">Ready: {state.file.name}</p>;
  }
  if (state.kind === "uploading") {
    return <p className="mt-3 text-sm text-slate-700">Uploading {state.file.name}...</p>;
  }
  if (state.kind === "accepted") {
    return (
      <div className="mt-3 rounded border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">
        <div className="flex items-center gap-2 font-medium">
          <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
          Accepted
        </div>
        <div className="mt-1">Source {state.response.source_id}</div>
        <div>Job {state.response.job_id}</div>
      </div>
    );
  }
  const tone = state.kind === "duplicate" || state.kind === "rejected" ? "amber" : "red";
  return (
    <div
      className={`mt-3 rounded border p-3 text-sm ${
        tone === "amber"
          ? "border-amber-200 bg-amber-50 text-amber-900"
          : "border-red-200 bg-red-50 text-red-800"
      }`}
    >
      <div className="flex items-center gap-2 font-medium">
        <AlertTriangle className="h-4 w-4" aria-hidden="true" />
        {state.kind}
      </div>
      <div className="mt-1">{state.message}</div>
    </div>
  );
}
