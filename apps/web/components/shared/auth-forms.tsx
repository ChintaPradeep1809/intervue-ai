"use client";

import type { User } from "@intervue/types";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { Spinner } from "@/components/shared/primitives";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, errorMessage } from "@/lib/api";
import { homeFor, useSession } from "@/lib/session";
import { cn } from "@/lib/utils";

function safeNext(next: string | null): string | null {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : null;
}

function GoogleButton() {
  const { config } = useSession();
  if (!config?.google_oauth) return null;
  return (
    <>
      <a href="/api/auth/google/start" className="inline-flex h-10 w-full items-center justify-center gap-2 rounded-lg border text-sm font-medium hover:bg-muted">
        <svg viewBox="0 0 24 24" className="size-4" aria-hidden>
          <path fill="#4285F4" d="M22.5 12.3c0-.8-.1-1.5-.2-2.3H12v4.3h5.9a5 5 0 0 1-2.2 3.3v2.7h3.5c2.1-1.9 3.3-4.7 3.3-8z" />
          <path fill="#34A853" d="M12 23c3 0 5.5-1 7.2-2.7l-3.5-2.7c-1 .7-2.2 1.1-3.7 1.1-2.9 0-5.3-1.9-6.2-4.5H2.2v2.8A11 11 0 0 0 12 23z" />
          <path fill="#FBBC05" d="M5.8 14.2a6.6 6.6 0 0 1 0-4.3V7.1H2.2a11 11 0 0 0 0 9.9l3.6-2.8z" />
          <path fill="#EA4335" d="M12 5.4c1.6 0 3.1.6 4.2 1.7l3.1-3.1A11 11 0 0 0 2.2 7.1l3.6 2.8C6.7 7.3 9.1 5.4 12 5.4z" />
        </svg>
        Continue with Google
      </a>
      <div className="flex items-center gap-3 text-xs text-muted-foreground">
        <span className="h-px flex-1 bg-border" /> or <span className="h-px flex-1 bg-border" />
      </div>
    </>
  );
}

export function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const { setUser } = useSession();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(params.get("error") ? "Sign-in with Google failed. Please try again." : null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const u = await api<User>("/auth/login", { body: { email, password } });
      setUser(u);
      router.replace(safeNext(params.get("next")) ?? homeFor(u));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold">Welcome back</h1>
        <p className="text-sm text-muted-foreground">Sign in to continue your interview practice.</p>
      </div>
      <GoogleButton />
      <form onSubmit={submit} className="space-y-4" noValidate>
        <div className="space-y-1.5">
          <Label htmlFor="email">Email</Label>
          <Input id="email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} className="h-10" />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="password">Password</Label>
          <Input id="password" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} className="h-10" />
        </div>
        {error && (
          <p role="alert" className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error}
          </p>
        )}
        <Button type="submit" className="h-10 w-full" disabled={busy || !email || !password}>
          {busy && <Spinner />} Sign in
        </Button>
      </form>
      <p className="text-center text-sm text-muted-foreground">
        New here?{" "}
        <Link href="/auth/register" className="font-medium text-foreground underline-offset-4 hover:underline">
          Create an account
        </Link>{" "}
        or{" "}
        <Link href="/demo" className="font-medium text-foreground underline-offset-4 hover:underline">
          try the demo
        </Link>
      </p>
    </div>
  );
}

export function RegisterForm() {
  const router = useRouter();
  const params = useSearchParams();
  const { setUser } = useSession();
  const [type, setType] = useState<"candidate" | "organization">(params.get("type") === "organization" ? "organization" : "candidate");
  const [form, setForm] = useState({ full_name: "", email: "", password: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const pwOk = form.password.length >= 8;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const u = await api<User>("/auth/register", { body: { ...form, account_type: type } });
      setUser(u);
      const next = safeNext(params.get("next"));
      router.replace(next ?? (type === "organization" ? "/organization/settings?setup=1" : "/onboarding"));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold">Create your account</h1>
        <p className="text-sm text-muted-foreground">Start with three free interviews. No card required.</p>
      </div>
      <div role="radiogroup" aria-label="Account type" className="grid grid-cols-2 gap-2 rounded-lg bg-muted p-1 text-sm">
        {(["candidate", "organization"] as const).map((t) => (
          <button
            key={t}
            type="button"
            role="radio"
            aria-checked={type === t}
            onClick={() => setType(t)}
            className={cn("rounded-md py-1.5 font-medium transition", type === t ? "bg-background shadow-sm" : "text-muted-foreground hover:text-foreground")}
          >
            {t === "candidate" ? "I'm a candidate" : "College / company"}
          </button>
        ))}
      </div>
      {type === "candidate" && <GoogleButton />}
      <form onSubmit={submit} className="space-y-4" noValidate>
        <div className="space-y-1.5">
          <Label htmlFor="name">Full name</Label>
          <Input id="name" autoComplete="name" required value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} className="h-10" />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="email">{type === "organization" ? "Work email" : "Email"}</Label>
          <Input id="email" type="email" autoComplete="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} className="h-10" />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="password">Password</Label>
          <Input
            id="password"
            type="password"
            autoComplete="new-password"
            required
            aria-describedby="pw-hint"
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
            className="h-10"
          />
          <p id="pw-hint" className={cn("text-xs", form.password && !pwOk ? "text-destructive" : "text-muted-foreground")}>
            At least 8 characters.
          </p>
        </div>
        {error && (
          <p role="alert" className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error}
          </p>
        )}
        <Button type="submit" className="h-10 w-full" disabled={busy || !form.full_name || !form.email || !pwOk}>
          {busy && <Spinner />} {type === "organization" ? "Create organization account" : "Create account"}
        </Button>
      </form>
      <p className="text-center text-sm text-muted-foreground">
        Already have an account?{" "}
        <Link href="/auth/login" className="font-medium text-foreground underline-offset-4 hover:underline">
          Sign in
        </Link>
      </p>
    </div>
  );
}
