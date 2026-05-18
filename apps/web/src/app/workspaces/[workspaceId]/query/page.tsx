"use client";

import { useParams } from "next/navigation";
import { QueryConsole } from "@/components/query-console";
import { useSession } from "@/lib/session";

export default function QueryPage() {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const { token, ready } = useSession({ required: true });

  if (!ready || !token) {
    return <div className="min-h-96" />;
  }

  return <QueryConsole workspaceId={workspaceId} token={token} />;
}
