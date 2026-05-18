"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

const TOKEN_KEY = "context-builder.operator-token";

let memoryToken: string | null = null;

export function getSessionToken(): string | null {
  if (memoryToken) {
    return memoryToken;
  }
  if (typeof window === "undefined") {
    return null;
  }
  memoryToken = window.sessionStorage.getItem(TOKEN_KEY);
  return memoryToken;
}

export function setSessionToken(token: string): void {
  memoryToken = token;
  if (typeof window !== "undefined") {
    window.sessionStorage.setItem(TOKEN_KEY, token);
    window.dispatchEvent(new Event("context-builder-session"));
  }
}

export function clearSessionToken(): void {
  memoryToken = null;
  if (typeof window !== "undefined") {
    window.sessionStorage.removeItem(TOKEN_KEY);
    window.dispatchEvent(new Event("context-builder-session"));
  }
}

export function useSession(options: { required?: boolean } = {}): {
  token: string | null;
  ready: boolean;
  signOut: () => void;
} {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const sync = () => {
      setToken(getSessionToken());
      setReady(true);
    };
    sync();
    window.addEventListener("storage", sync);
    window.addEventListener("context-builder-session", sync);
    return () => {
      window.removeEventListener("storage", sync);
      window.removeEventListener("context-builder-session", sync);
    };
  }, []);

  useEffect(() => {
    if (ready && options.required && !token) {
      router.replace("/login");
    }
  }, [options.required, ready, router, token]);

  return {
    token,
    ready,
    signOut: () => {
      clearSessionToken();
      router.replace("/login");
    }
  };
}
