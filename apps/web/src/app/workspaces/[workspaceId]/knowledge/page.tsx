"use client";

import { useParams } from "next/navigation";
import { KnowledgeConsole } from "@/components/knowledge-console";
import { useSession } from "@/lib/session";

export default function KnowledgePage() {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const { token, ready } = useSession({ required: true });

  if (!ready || !token) {
    return <div className="min-h-96" />;
  }

  return <KnowledgeConsole workspaceId={workspaceId} token={token} />;
}
