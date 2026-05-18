"use client";

import { useParams } from "next/navigation";
import { UnknownConsole } from "@/components/unknown-console";
import { useSession } from "@/lib/session";

export default function UnknownPage() {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const { token, ready } = useSession({ required: true });

  if (!ready || !token) {
    return <div className="min-h-96" />;
  }

  return <UnknownConsole workspaceId={workspaceId} token={token} />;
}
