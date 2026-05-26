"use client";

import { useParams } from "next/navigation";
import { ContextBuildWizard } from "@/components/context-build-wizard";
import { useSession } from "@/lib/session";

export default function ContextBuildPage() {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const { token, ready } = useSession({ required: true });

  if (!ready || !token) {
    return <div className="min-h-96" />;
  }

  return <ContextBuildWizard workspaceId={workspaceId} token={token} />;
}
