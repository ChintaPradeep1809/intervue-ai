"use client";

import type { PublicConfig, User } from "@intervue/types";
import { createContext, useCallback, useContext, useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api";

interface SessionValue {
  user: User | null;
  loading: boolean;
  config: PublicConfig | null;
  refresh: () => Promise<User | null>;
  logout: () => Promise<void>;
  setUser: (u: User | null) => void;
}

const SessionContext = createContext<SessionValue | null>(null);

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [config, setConfig] = useState<PublicConfig | null>(null);

  const refresh = useCallback(async () => {
    try {
      const u = await api<User>("/auth/me");
      setUser(u);
      return u;
    } catch (e) {
      if (!(e instanceof ApiError) || e.status === 401) setUser(null);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  const logout = useCallback(async () => {
    await api("/auth/logout", { method: "POST" }).catch(() => undefined);
    setUser(null);
  }, []);

  useEffect(() => {
    api<User>("/auth/me")
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false));
    api<PublicConfig>("/config")
      .then(setConfig)
      .catch(() => undefined);
  }, []);

  return (
    <SessionContext.Provider value={{ user, loading, config, refresh, logout, setUser }}>
      {children}
    </SessionContext.Provider>
  );
}

export function useSession(): SessionValue {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used inside SessionProvider");
  return ctx;
}

export function homeFor(user: User | null): string {
  if (!user) return "/auth/login";
  if (user.role === "super_admin") return "/admin";
  if (user.role === "organization_admin")
    return user.organizations.some((o) => o.role === "admin") ? "/organization" : "/organization/settings";
  if (!user.onboarding_completed) return "/onboarding";
  return "/dashboard";
}
