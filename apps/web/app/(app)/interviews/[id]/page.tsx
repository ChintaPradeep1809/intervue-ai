"use client";

import type { InterviewDetail } from "@intervue/types";
import { Code2 } from "lucide-react";
import { useParams } from "next/navigation";
import { useState } from "react";

import { primaryAction } from "@/components/interview/interview-list";
import { PlanView } from "@/components/interview/plan-view";
import { TranscriptView } from "@/components/reports/transcript-view";
import { ErrorState, LinkButton, LoadingBlock, PageHeader, StatusBadge } from "@/components/shared/primitives";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { formatDateTime } from "@/lib/format";
import { useApi } from "@/lib/use-api";

export default function InterviewOverviewPage() {
  const { id } = useParams<{ id: string }>();
  const { data: iv, error, loading, reload } = useApi<InterviewDetail>(`/interviews/${id}`);
  const [tab, setTab] = useState("plan");
  if (loading) return <LoadingBlock rows={4} />;
  if (error || !iv) return <ErrorState message={error?.message ?? "Interview not found."} onRetry={reload} />;
  const a = primaryAction(iv);
  const hasCoding = iv.plan.rounds.some((r) => r.kind === "coding" || r.kind === "sql");
  return (
    <>
      <PageHeader
        eyebrow={<StatusBadge status={iv.status} />}
        title={iv.title}
        description={`Created ${formatDateTime(iv.created_at)}${iv.completed_at ? ` · Completed ${formatDateTime(iv.completed_at)}` : ""}`}
        actions={
          <>
            {hasCoding && iv.status !== "planned" && (
              <LinkButton href={`/interviews/${iv.id}/coding`} variant="outline" className="h-9">
                <Code2 className="size-4" /> Code
              </LinkButton>
            )}
            <LinkButton href={a.href} className="h-9">
              <a.icon className="size-4" /> {a.label}
            </LinkButton>
          </>
        }
      />
      <Tabs value={tab} onValueChange={(v) => setTab(String(v))}>
        <TabsList>
          <TabsTrigger value="plan">Plan</TabsTrigger>
          <TabsTrigger value="transcript" disabled={iv.status === "planned"}>
            Transcript
          </TabsTrigger>
        </TabsList>
        <TabsContent value="plan" className="pt-4">
          <PlanView plan={iv.plan} analysis={iv.analysis} />
        </TabsContent>
        <TabsContent value="transcript" className="pt-4">
          {tab === "transcript" && <TranscriptView interviewId={iv.id} />}
        </TabsContent>
      </Tabs>
    </>
  );
}
