"use client";

import { useState } from "react";
import { Download, Loader2, ShieldAlert, Trash2 } from "lucide-react";
import { AlertMessage, Pill, StatusBadge } from "@/components/console-primitives";
import { apiFetch, apiMessage } from "@/lib/api";

type PrivacyConsoleProps = {
  workspaceId: string;
  token: string;
};

type PrivacyRequestResponse = {
  request_id: string;
  request_type: string;
  status: string;
  dry_run: boolean;
  deletion_plan: Record<string, number>;
  report?: Record<string, number | boolean | string>;
};

type BusyAction = "export" | "delete_dry_run" | "delete_confirm" | null;
const DELETE_CONFIRMATION_PHRASE = "DELETE_WORKSPACE_METADATA";

export function PrivacyConsole({ workspaceId, token }: PrivacyConsoleProps) {
  const [busy, setBusy] = useState<BusyAction>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<PrivacyRequestResponse | null>(null);
  const [confirmationText, setConfirmationText] = useState("");

  async function createExportRequest() {
    setBusy("export");
    setError(null);
    setResult(null);
    try {
      setResult(
        await apiFetch<PrivacyRequestResponse>(`/workspaces/${workspaceId}/privacy/export`, {
          token,
          method: "POST"
        })
      );
    } catch (caught) {
      setError(apiMessage(caught));
    } finally {
      setBusy(null);
    }
  }

  async function createDeleteRequest() {
    setBusy("delete_dry_run");
    setError(null);
    setResult(null);
    try {
      setResult(
        await apiFetch<PrivacyRequestResponse>(`/workspaces/${workspaceId}/privacy/delete-request`, {
          token,
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({})
        })
      );
    } catch (caught) {
      setError(apiMessage(caught));
    } finally {
      setBusy(null);
    }
  }

  async function confirmDeleteRequest() {
    if (!result || result.request_type !== "delete") {
      setError("Generate a delete dry-run before confirming.");
      return;
    }
    setBusy("delete_confirm");
    setError(null);
    try {
      setResult(
        await apiFetch<PrivacyRequestResponse>(
          `/workspaces/${workspaceId}/privacy/delete-request/${result.request_id}/confirm`,
          {
            token,
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ confirmation: DELETE_CONFIRMATION_PHRASE })
          }
        )
      );
      setConfirmationText("");
    } catch (caught) {
      setError(apiMessage(caught));
    } finally {
      setBusy(null);
    }
  }

  const canConfirmDelete =
    result?.request_type === "delete" &&
    result.dry_run &&
    confirmationText === DELETE_CONFIRMATION_PHRASE;

  return (
    <section className="mx-auto max-w-5xl text-slate-950">
      <div className="mb-5">
        <h1 className="text-2xl font-semibold">Settings</h1>
        <p className="text-sm text-slate-600">
          Owner-only workspace privacy controls for export and LGPD deletion requests.
        </p>
      </div>

      {error ? <AlertMessage tone="error">{error}</AlertMessage> : null}

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded border border-slate-200 bg-white p-4">
          <div className="flex items-start gap-3">
            <Download className="mt-0.5 h-5 w-5 text-slate-500" aria-hidden="true" />
            <div>
              <h2 className="text-base font-semibold">Export workspace data</h2>
              <p className="mt-1 text-sm leading-6 text-slate-600">
                Creates an auditable export request for this workspace. The backend records the request and keeps it scoped to the workspace.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => void createExportRequest()}
            disabled={Boolean(busy)}
            className="mt-4 inline-flex h-9 items-center gap-2 rounded bg-slate-950 px-3 text-sm font-medium text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            {busy === "export" ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Download className="h-4 w-4" aria-hidden="true" />}
            Request export
          </button>
        </div>

        <div className="rounded border border-amber-200 bg-white p-4">
          <div className="flex items-start gap-3">
            <ShieldAlert className="mt-0.5 h-5 w-5 text-amber-700" aria-hidden="true" />
            <div>
              <h2 className="text-base font-semibold">Delete request dry-run</h2>
              <p className="mt-1 text-sm leading-6 text-slate-600">
                Start with a dry-run deletion plan. Confirmed deletion remains explicit and audited.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => void createDeleteRequest()}
            disabled={Boolean(busy)}
            className="mt-4 inline-flex h-9 items-center gap-2 rounded border border-slate-300 bg-white px-3 text-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy === "delete_dry_run" ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Trash2 className="h-4 w-4" aria-hidden="true" />}
            Generate dry-run
          </button>

          <div className="mt-4 border-t border-slate-200 pt-4">
            <label className="text-sm font-medium">
              Confirm delete phrase
              <input
                value={confirmationText}
                onChange={(event) => setConfirmationText(event.target.value)}
                placeholder={DELETE_CONFIRMATION_PHRASE}
                className="mt-1 h-10 w-full rounded border border-slate-300 px-3 text-sm font-normal outline-none focus:border-slate-950"
              />
            </label>
            <button
              type="button"
              onClick={() => void confirmDeleteRequest()}
              disabled={Boolean(busy) || !canConfirmDelete}
              className="mt-3 inline-flex h-9 items-center gap-2 rounded bg-red-700 px-3 text-sm font-medium text-white hover:bg-red-800 disabled:cursor-not-allowed disabled:bg-red-200"
            >
              {busy === "delete_confirm" ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Trash2 className="h-4 w-4" aria-hidden="true" />}
              Confirm delete request
            </button>
          </div>
        </div>
      </div>

      {result ? <PrivacyResult result={result} /> : null}
    </section>
  );
}

function PrivacyResult({ result }: { result: PrivacyRequestResponse }) {
  return (
    <div className="mt-4 rounded border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <Pill>{result.request_type}</Pill>
        <StatusBadge value={result.status} />
        {result.dry_run ? <Pill tone="amber">dry run</Pill> : null}
      </div>
      <p className="mt-3 break-all text-sm text-slate-600">Request {result.request_id}</p>
      <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
        {Object.entries(result.report ?? result.deletion_plan).map(([key, value]) => (
          <div key={key} className="rounded border border-slate-200 bg-slate-50 p-3">
            <dt className="text-xs font-medium uppercase text-slate-500">{key.replaceAll("_", " ")}</dt>
            <dd className="mt-1 text-lg font-semibold text-slate-950">{String(value)}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
