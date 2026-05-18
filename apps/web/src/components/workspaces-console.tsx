"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, Database, LogOut, Plus, RefreshCw } from "lucide-react";
import { AlertMessage, EmptyState, LoadingState, Panel, StatusBadge } from "@/components/console-primitives";
import { apiFetch, apiMessage, type Workspace } from "@/lib/api";
import { formatDate } from "@/lib/format";

type WorkspacesConsoleProps = {
  token: string;
  onSignOut: () => void;
};

export function WorkspacesConsole({ token, onSignOut }: WorkspacesConsoleProps) {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");

  const loadWorkspaces = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setWorkspaces(await apiFetch<Workspace[]>("/workspaces", { token }));
    } catch (caught) {
      setError(apiMessage(caught));
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void loadWorkspaces();
  }, [loadWorkspaces]);

  async function createWorkspace(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!name.trim()) {
      return;
    }
    setError(null);
    try {
      const created = await apiFetch<Workspace>("/workspaces", {
        token,
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim(), slug: slug.trim() || null })
      });
      setWorkspaces((current) => [created, ...current]);
      setName("");
      setSlug("");
    } catch (caught) {
      setError(apiMessage(caught));
    }
  }

  return (
    <main className="min-h-screen bg-slate-100 text-slate-950">
      <div className="mx-auto max-w-6xl px-6 py-6">
        <header className="mb-6 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold">Workspaces</h1>
            <p className="text-sm text-slate-600">Choose the tenant surface to operate.</p>
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => void loadWorkspaces()}
              className="inline-flex h-9 items-center gap-2 rounded border border-slate-300 bg-white px-3 text-sm hover:bg-slate-50"
            >
              <RefreshCw className="h-4 w-4" aria-hidden="true" />
              Refresh
            </button>
            <button
              type="button"
              onClick={onSignOut}
              className="inline-flex h-9 items-center gap-2 rounded border border-slate-300 bg-white px-3 text-sm hover:bg-slate-50"
            >
              <LogOut className="h-4 w-4" aria-hidden="true" />
              Sign out
            </button>
          </div>
        </header>

        {error ? <AlertMessage tone="error">{error}</AlertMessage> : null}

        <form onSubmit={createWorkspace} className="mb-5 grid gap-3 rounded border border-slate-200 bg-white p-4 md:grid-cols-[1fr_220px_auto]">
          <label className="sr-only" htmlFor="workspace-name">
            Workspace name
          </label>
          <input
            id="workspace-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Workspace name"
            className="h-10 rounded border border-slate-300 px-3 text-sm outline-none focus:border-slate-950"
          />
          <label className="sr-only" htmlFor="workspace-slug">
            Optional slug
          </label>
          <input
            id="workspace-slug"
            value={slug}
            onChange={(event) => setSlug(event.target.value)}
            placeholder="Optional slug"
            className="h-10 rounded border border-slate-300 px-3 text-sm outline-none focus:border-slate-950"
          />
          <button type="submit" className="inline-flex h-10 items-center justify-center gap-2 rounded bg-slate-950 px-4 text-sm font-medium text-white hover:bg-slate-800">
            <Plus className="h-4 w-4" aria-hidden="true" />
            Create
          </button>
        </form>

        <Panel className="overflow-hidden">
          <div className="grid grid-cols-[1fr_120px_180px_44px] border-b border-slate-200 bg-slate-50 px-4 py-2 text-xs font-medium uppercase tracking-wide text-slate-500">
            <span>Name</span>
            <span>Status</span>
            <span>Created</span>
            <span />
          </div>
          {loading ? (
            <LoadingState>Loading workspaces...</LoadingState>
          ) : workspaces.length === 0 ? (
            <EmptyState icon={<Database className="h-5 w-5" aria-hidden="true" />}>
              No workspaces available for this operator token.
            </EmptyState>
          ) : (
            workspaces.map((workspace) => (
              <Link
                key={workspace.id}
                href={`/workspaces/${workspace.id}`}
                className="grid grid-cols-[1fr_120px_180px_44px] items-center border-b border-slate-100 px-4 py-3 text-sm last:border-b-0 hover:bg-slate-50"
              >
                <span>
                  <span className="block font-medium">{workspace.name}</span>
                  <span className="block text-xs text-slate-500">{workspace.slug ?? workspace.id}</span>
                </span>
                <StatusBadge value={workspace.status} />
                <span className="text-slate-600">{formatDate(workspace.created_at)}</span>
                <ArrowRight className="h-4 w-4 text-slate-500" aria-hidden="true" />
              </Link>
            ))
          )}
        </Panel>
      </div>
    </main>
  );
}
