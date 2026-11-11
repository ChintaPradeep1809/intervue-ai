"use client";

import { Logo } from "@/components/brand/logo";
import { InterviewWizard } from "@/components/interview/interview-wizard";
import { Spinner } from "@/components/shared/primitives";
import { useSession } from "@/lib/session";

export default function OnboardingPage() {
  const { user, loading } = useSession();
  return (
    <div className="min-h-screen bg-muted/30">
      <header className="flex h-16 items-center justify-between border-b bg-background px-4 sm:px-8">
        <Logo />
        <span className="text-sm text-muted-foreground">Set up your first interview</span>
      </header>
      <main id="main" className="px-4 py-10">
        {loading || !user ? (
          <div className="grid place-items-center py-20">
            <Spinner className="size-5" />
          </div>
        ) : (
          <InterviewWizard includeProfile />
        )}
      </main>
    </div>
  );
}
