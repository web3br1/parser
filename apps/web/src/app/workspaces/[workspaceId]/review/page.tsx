"use client";

import { useParams } from "next/navigation";
import { ReviewConsole } from "@/components/review-console";
import { useSession } from "@/lib/session";

export default function ReviewPage() {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const { token, ready } = useSession({ required: true });

  if (!ready || !token) {
    return <div className="min-h-96" />;
  }

  return <ReviewConsole workspaceId={workspaceId} token={token} />;
}
