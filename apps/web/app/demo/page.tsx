"use client";

import type { InterviewDetail } from "@intervue/types";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { Logo } from "@/components/brand/logo";
import { LinkButton, Spinner } from "@/components/shared/primitives";
import { api, errorMessage } from "@/lib/api";
import { useSession } from "@/lib/session";

/** "Try a Demo": creates a guest session with a short AWS Data Engineer interview. */
export default function DemoPage() {
  const router = useRouter();
  const { refresh } = useSession();
  const [error, setError] = useState<string | null>(null);
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    api<InterviewDetail>("/demo/start", { method: "POST" })
      .then(async (iv) => {
        await refresh();
        router.replace(`/interviews/${iv.id}/setup`);
      })
      .catch((e) => setError(errorMessage(e)));
  }, [router, refresh]);

  return (
    <div className="grid min-h-screen place-items-center px-4">
      <div className="max-w-sm space-y-5 text-center">
        <Logo className="justify-center" />
        {error ? (
          <>
            <p className="text-sm text-destructive">{error}</p>
            <LinkButton href="/">Back to home</LinkButton>
          </>
        ) : (
          <>
            <Spinner className="mx-auto size-6 text-primary" />
            <div>
              <p className="font-medium">Preparing your demo interview</p>
              <p className="mt-1 text-sm text-muted-foreground">AWS Data Engineer · about 8 minutes · SQL, PySpark and behavioral questions</p>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
