"use client";

import { ErrorState, LoadingBlock } from "@/components/shared/primitives";
import { formatDateTime } from "@/lib/format";
import { useApi } from "@/lib/use-api";
import { cn } from "@/lib/utils";

interface Line {
  speaker: "interviewer" | "candidate" | "system";
  kind: string;
  text: string;
  at: string;
}

export function TranscriptView({ interviewId }: { interviewId: string }) {
  const { data, error, loading, reload } = useApi<{ items: Line[] }>(`/interviews/${interviewId}/transcript`);
  if (loading) return <LoadingBlock rows={4} />;
  if (error) return <ErrorState message={error.message} onRetry={reload} />;
  const items = data?.items ?? [];
  if (!items.length) return <p className="text-sm text-muted-foreground">No transcript yet.</p>;
  return (
    <ol className="space-y-3" aria-label="Interview transcript">
      {items.map((l, i) => (
        <li key={i} className={cn("flex gap-3", l.speaker === "candidate" && "flex-row-reverse")}>
          <div
            className={cn(
              "max-w-[85%] rounded-2xl px-4 py-2.5 text-sm",
              l.speaker === "candidate" ? "rounded-tr-sm bg-primary text-primary-foreground" : "rounded-tl-sm bg-muted",
            )}
          >
            <p className="mb-0.5 text-[11px] opacity-70">
              {l.speaker === "candidate" ? `You${l.kind === "typed" ? " (typed)" : ""}` : "Interviewer"} · {formatDateTime(l.at)}
            </p>
            <p className="whitespace-pre-wrap">{l.text}</p>
          </div>
        </li>
      ))}
    </ol>
  );
}
