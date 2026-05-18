"use client";

import { WorkspacesConsole } from "@/components/workspaces-console";
import { useSession } from "@/lib/session";

export default function WorkspacesPage() {
  const { token, ready, signOut } = useSession({ required: true });

  if (!ready || !token) {
    return <main className="min-h-screen bg-slate-100" />;
  }

  return <WorkspacesConsole token={token} onSignOut={signOut} />;
}
