"use client";

import { useParams } from "next/navigation";
import { SourceDetail } from "@/components/source-detail";
import { useSession } from "@/lib/session";

export default function SourceDetailPage() {
  const { workspaceId, sourceId } = useParams<{ workspaceId: string; sourceId: string }>();
  const { token, ready } = useSession({ required: true });

  if (!ready || !token) {
    return <div className="min-h-96" />;
  }

  return <SourceDetail workspaceId={workspaceId} sourceId={sourceId} token={token} />;
}
