"use client";

import type { ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Info, Loader2 } from "lucide-react";

export type PillTone = "amber" | "emerald" | "red" | "sky" | "slate" | "violet";
type AlertTone = "error" | "success" | "warning" | "info";

const pillStyles: Record<PillTone, string> = {
  amber: "bg-amber-50 text-amber-800 ring-amber-200",
  emerald: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  red: "bg-red-50 text-red-700 ring-red-200",
  sky: "bg-sky-50 text-sky-700 ring-sky-200",
  slate: "bg-slate-100 text-slate-700 ring-slate-200",
  violet: "bg-violet-50 text-violet-700 ring-violet-200"
};

const alertStyles: Record<AlertTone, string> = {
  error: "border-red-200 bg-red-50 text-red-800",
  success: "border-emerald-200 bg-emerald-50 text-emerald-800",
  warning: "border-amber-200 bg-amber-50 text-amber-900",
  info: "border-sky-200 bg-sky-50 text-sky-800"
};

export function Pill({ tone = "slate", children }: { tone?: PillTone; children: ReactNode }) {
  return <span className={`w-fit rounded px-2 py-1 text-xs font-medium ring-1 ${pillStyles[tone]}`}>{children}</span>;
}

export function StatusBadge({ value, tone }: { value: string; tone?: PillTone }) {
  return <Pill tone={tone ?? toneForStatus(value)}>{value.replaceAll("_", " ")}</Pill>;
}

export function AlertMessage({ tone, children }: { tone: AlertTone; children: ReactNode }) {
  return (
    <div className={`mb-4 rounded border p-3 text-sm ${alertStyles[tone]}`}>
      <div className="flex gap-2">
        {tone === "success" ? (
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        ) : tone === "info" ? (
          <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        ) : (
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        )}
        <span>{children}</span>
      </div>
    </div>
  );
}

export function LoadingState({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-center gap-2 p-4 text-sm text-slate-600">
      <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
      {children}
    </div>
  );
}

export function EmptyState({ icon, children }: { icon?: ReactNode; children: ReactNode }) {
  return (
    <div className="flex items-center gap-3 p-6 text-sm text-slate-600">
      {icon}
      <span>{children}</span>
    </div>
  );
}

export function Panel({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`rounded border border-slate-200 bg-white ${className}`}>{children}</div>;
}

export function PanelHeader({ children }: { children: ReactNode }) {
  return (
    <div className="border-b border-slate-200 bg-slate-50 px-4 py-2 text-xs font-medium uppercase tracking-wide text-slate-500">
      {children}
    </div>
  );
}

function toneForStatus(value: string): PillTone {
  if (["valid_answer", "mapped", "approved", "published", "completed", "success"].includes(value)) {
    return "emerald";
  }
  if (["failed", "rejected", "unvalidated_data", "error"].includes(value)) {
    return "red";
  }
  if (["running", "processing", "extracted", "open"].includes(value)) {
    return "sky";
  }
  if (["unknown", "needs_review", "needs_human_validation", "conflicting_sources", "queued", "retrying"].includes(value)) {
    return "amber";
  }
  return "slate";
}
