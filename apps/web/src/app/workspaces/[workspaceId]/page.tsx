"use client";

import { useParams } from "next/navigation";
import { WorkspaceDashboard } from "@/components/workspace-dashboard";
import { useSession } from "@/lib/session";

export default function WorkspaceHomePage() {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const { token, ready } = useSession({ required: true });

  if (!ready || !token) {
    return <div className="min-h-96" />;
  }

  return <WorkspaceDashboard workspaceId={workspaceId} token={token} />;
}
