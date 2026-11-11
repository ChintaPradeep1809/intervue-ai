"use client";

import type { InterviewDetail } from "@intervue/types";
import { Building2, Clock, ShieldCheck } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Logo } from "@/components/brand/logo";
import { ErrorState, LinkButton, LoadingBlock, Spinner } from "@/components/shared/primitives";
import { Button } from "@/components/ui/button";
import { api, errorMessage } from "@/lib/api";
import { useSession } from "@/lib/session";
import { useApi } from "@/lib/use-api";

interface InviteView {
  organization: { name: string; kind: string };
  template: { name: string; role_title: string; duration_minutes: number; interview_type: string; difficulty: string; rounds: { title: string; kind: string; minutes: number }[] };
  email_domain: string | null;
}

/** College/company invite: open link → verify identity (sign in) → consent & system check → interview → result. */
export default function InvitePage() {
  const { token } = useParams<{ token: string }>();
  const router = useRouter();
  const { user, loading: sessionLoading } = useSession();
  const { data, error, loading } = useApi<InviteView>(`/invites/${token}`);
  const [busy, setBusy] = useState(false);
  const next = `/invite/${token}`;

  async function accept() {
    setBusy(true);
    try {
      const iv = await api<InterviewDetail>(`/invites/${token}/accept`, { method: "POST" });
      router.push(`/interviews/${iv.id}/setup`);
    } catch (e) {
      toast.error(errorMessage(e));
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-muted/30">
      <header className="flex h-16 items-center border-b bg-background px-4 sm:px-8">
        <Logo />
      </header>
      <main id="main" className="mx-auto max-w-xl px-4 py-12">
        {loading ? (
          <LoadingBlock rows={2} />
        ) : error || !data ? (
          <ErrorState message={error?.message ?? "Invite not found."} />
        ) : (
          <div className="space-y-6 rounded-2xl border bg-card p-8">
            <div className="flex items-center gap-3">
              <span className="grid size-11 place-items-center rounded-xl bg-accent">
                <Building2 className="size-5 text-accent-foreground" />
              </span>
              <div>
                <p className="text-sm text-muted-foreground">{data.organization.name} invited you to</p>
                <h1 className="text-xl font-semibold">{data.template.name}</h1>
              </div>
            </div>
            <div className="flex flex-wrap gap-4 text-sm text-muted-foreground">
              <span className="inline-flex items-center gap-1.5">
                <Clock className="size-4" /> {data.template.duration_minutes} minutes
              </span>
              <span>{data.template.role_title}</span>
              <span className="capitalize">{data.template.difficulty}</span>
            </div>
            <ol className="space-y-1.5 text-sm">
              {data.template.rounds.map((r, i) => (
                <li key={i} className="flex justify-between rounded-lg bg-muted/50 px-3 py-2">
                  <span>
                    {i + 1}. {r.title}
                  </span>
                  <span className="text-muted-foreground">{r.minutes} min</span>
                </li>
              ))}
            </ol>
            <p className="flex gap-2 text-xs text-muted-foreground">
              <ShieldCheck className="size-4 shrink-0" /> Your results are shared with {data.organization.name}. They are AI-assisted and reviewed by people before any decision.
            </p>
            {sessionLoading ? (
              <Spinner />
            ) : user ? (
              <div className="space-y-2">
                <p className="text-sm">
                  Signed in as <span className="font-medium">{user.email}</span>
                  {data.email_domain && <span className="text-muted-foreground"> (requires @{data.email_domain})</span>}
                </p>
                <Button className="h-11 w-full" onClick={accept} disabled={busy}>
                  {busy && <Spinner />} Continue to system check
                </Button>
              </div>
            ) : (
              <div className="grid gap-2 sm:grid-cols-2">
                <LinkButton href={`/auth/register?next=${encodeURIComponent(next)}`} className="h-10">
                  Create account
                </LinkButton>
                <LinkButton href={`/auth/login?next=${encodeURIComponent(next)}`} variant="outline" className="h-10">
                  Sign in
                </LinkButton>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
