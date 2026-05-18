"use client";

import { useParams } from "next/navigation";
import { PrivacyConsole } from "@/components/privacy-console";
import { useSession } from "@/lib/session";

export default function SettingsPage() {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const { token, ready } = useSession({ required: true });

  if (!ready || !token) {
    return <div className="min-h-96" />;
  }

  return <PrivacyConsole workspaceId={workspaceId} token={token} />;
}
