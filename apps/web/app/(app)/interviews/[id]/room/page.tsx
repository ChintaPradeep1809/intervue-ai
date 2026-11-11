"use client";

import type { InterviewDetail } from "@intervue/types";
import { useParams } from "next/navigation";

import { InterviewRoom } from "@/components/interview/interview-room";
import { ErrorState, LinkButton, Spinner } from "@/components/shared/primitives";
import { useApi } from "@/lib/use-api";

export default function RoomPage() {
  const { id } = useParams<{ id: string }>();
  const { data, error, loading, reload } = useApi<InterviewDetail>(`/interviews/${id}`);
  if (loading)
    return (
      <div className="grid min-h-screen place-items-center bg-studio text-studio-foreground">
        <Spinner className="size-6" />
      </div>
    );
  if (error || !data)
    return (
      <div className="mx-auto max-w-md p-10">
        <ErrorState message={error?.message ?? "Interview not found."} onRetry={reload} />
      </div>
    );
  if (!data.consent?.accepted && data.status === "planned")
    return (
      <div className="mx-auto max-w-md space-y-4 p-10 text-center">
        <p>Please complete the system check and consent before entering the room.</p>
        <LinkButton href={`/interviews/${id}/setup`}>Go to setup</LinkButton>
      </div>
    );
  return <InterviewRoom interview={data} />;
}
