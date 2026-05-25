"use client";

import { FormEvent, useEffect, useState } from "react";
import { KeyRound, ShieldCheck } from "lucide-react";
import { useRouter } from "next/navigation";
import { getSessionToken, setSessionToken } from "@/lib/session";

export default function LoginPage() {
  const router = useRouter();
  const [token, setToken] = useState("");

  useEffect(() => {
    if (getSessionToken()) {
      router.replace("/workspaces");
    }
  }, [router]);

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = token.trim();
    if (!trimmed) {
      return;
    }
    setSessionToken(trimmed);
    router.replace("/workspaces");
  }

  return (
    <main className="min-h-screen bg-slate-100 text-slate-950">
      <section className="mx-auto flex min-h-screen w-full max-w-md flex-col justify-center px-6">
        <div className="mb-8 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded bg-slate-950 text-white">
            <ShieldCheck className="h-5 w-5" aria-hidden="true" />
          </div>
          <div>
            <h1 className="text-xl font-semibold">Parser</h1>
            <p className="text-sm text-slate-600">Internal operator console</p>
          </div>
        </div>

        <form onSubmit={onSubmit} className="rounded border border-slate-200 bg-white p-6 shadow-sm">
          <label htmlFor="token" className="block text-sm font-medium text-slate-700">
            Operator bearer token
          </label>
          <div className="mt-2 flex items-center gap-2 rounded border border-slate-300 bg-white px-3 focus-within:border-slate-950">
            <KeyRound className="h-4 w-4 text-slate-500" aria-hidden="true" />
            <input
              id="token"
              type="password"
              autoComplete="off"
              value={token}
              onChange={(event) => setToken(event.target.value)}
              className="h-11 min-w-0 flex-1 bg-transparent text-sm outline-none"
              placeholder="Paste user access token"
            />
          </div>
          <p className="mt-3 text-sm leading-6 text-slate-600">
            Use a normal authenticated user token for this workspace. Do not paste service-role keys.
          </p>
          <button
            type="submit"
            className="mt-5 inline-flex h-10 w-full items-center justify-center rounded bg-slate-950 px-4 text-sm font-medium text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300"
            disabled={!token.trim()}
          >
            Enter console
          </button>
        </form>
      </section>
    </main>
  );
}
