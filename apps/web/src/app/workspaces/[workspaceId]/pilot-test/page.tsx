"use client";

import { useParams } from "next/navigation";
import { PilotTestConsole } from "@/components/pilot-test-console";
import { useSession } from "@/lib/session";

export default function PilotTestPage() {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const { token, ready } = useSession({ required: true });

  if (!ready || !token) {
    return <div className="min-h-96" />;
  }

  return <PilotTestConsole workspaceId={workspaceId} token={token} />;
}
