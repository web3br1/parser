"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { useParams, usePathname } from "next/navigation";
import {
  Archive,
  BookOpen,
  Database,
  HelpCircle,
  LayoutDashboard,
  type LucideIcon,
  LogOut,
  Settings,
  ShieldQuestion
} from "lucide-react";
import { useSession } from "@/lib/session";

type NavItem = {
  label: string;
  href: string;
  icon: LucideIcon;
  disabled?: boolean;
};

const navItems: NavItem[] = [
  { label: "Dashboard", href: "", icon: LayoutDashboard },
  { label: "Sources", href: "sources", icon: Database },
  { label: "Review Queue", href: "review", icon: Archive },
  { label: "Unknown Items", href: "unknown", icon: ShieldQuestion },
  { label: "Knowledge Base", href: "knowledge", icon: BookOpen },
  { label: "Query", href: "query", icon: HelpCircle },
  { label: "Settings", href: "settings", icon: Settings }
];

export function WorkspaceShell({ children }: { children: ReactNode }) {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const pathname = usePathname();
  const { ready, token, signOut } = useSession({ required: true });

  if (!ready || !token) {
    return <div className="min-h-screen bg-slate-100" />;
  }

  return (
    <div className="min-h-screen bg-slate-100 text-slate-950">
      <div className="flex min-h-screen">
        <aside className="hidden w-64 shrink-0 border-r border-slate-200 bg-white lg:block">
          <div className="border-b border-slate-200 px-5 py-5">
            <Link href="/workspaces" className="text-sm font-semibold text-slate-950">
              Context Builder
            </Link>
            <p className="mt-1 truncate text-xs text-slate-500">Workspace {workspaceId}</p>
          </div>
          <nav className="px-3 py-4">
            {navItems.map((item) => {
              const href = item.href ? `/workspaces/${workspaceId}/${item.href}` : `/workspaces/${workspaceId}`;
              const active = item.href ? pathname === href || pathname.startsWith(`${href}/`) : pathname === href;
              const Icon = item.icon;
              const className = [
                "mb-1 flex h-10 items-center gap-3 rounded px-3 text-sm",
                active ? "bg-slate-950 text-white" : "text-slate-700 hover:bg-slate-100",
                item.disabled ? "pointer-events-none opacity-45" : ""
              ].join(" ");
              return (
                <Link
                  key={item.href}
                  href={item.disabled ? pathname : href}
                  aria-disabled={item.disabled ? "true" : undefined}
                  className={className}
                >
                  <Icon className="h-4 w-4" aria-hidden="true" />
                  <span>{item.label}</span>
                </Link>
              );
            })}
          </nav>
        </aside>

        <div className="min-w-0 flex-1">
          <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/95 px-4 py-3 backdrop-blur md:px-6">
            <div className="flex items-center justify-between gap-4">
              <div className="min-w-0">
                <div className="flex items-center gap-2 text-xs text-slate-500">
                  <Link href="/workspaces" className="hover:text-slate-950">
                    Workspaces
                  </Link>
                  <span>/</span>
                  <span className="truncate">{workspaceId}</span>
                </div>
                <h1 className="mt-1 truncate text-base font-semibold text-slate-950">
                  Operator Console
                </h1>
              </div>
              <button
                type="button"
                onClick={signOut}
                className="inline-flex h-9 items-center gap-2 rounded border border-slate-300 bg-white px-3 text-sm text-slate-700 hover:bg-slate-50"
              >
                <LogOut className="h-4 w-4" aria-hidden="true" />
                Sign out
              </button>
            </div>
            <nav className="mt-3 flex gap-2 overflow-x-auto pb-1 lg:hidden">
              {navItems.map((item) => {
                const href = item.href ? `/workspaces/${workspaceId}/${item.href}` : `/workspaces/${workspaceId}`;
                const active = item.href ? pathname === href || pathname.startsWith(`${href}/`) : pathname === href;
                return (
                  <Link
                    key={item.href}
                    href={item.disabled ? pathname : href}
                    aria-disabled={item.disabled ? "true" : undefined}
                    className={`shrink-0 rounded px-3 py-1.5 text-sm ${
                      active ? "bg-slate-950 text-white" : "bg-slate-100 text-slate-700"
                    } ${item.disabled ? "pointer-events-none opacity-45" : ""}`}
                  >
                    {item.label}
                  </Link>
                );
              })}
            </nav>
          </header>
          <div className="px-4 py-6 md:px-6">{children}</div>
        </div>
      </div>
    </div>
  );
}
