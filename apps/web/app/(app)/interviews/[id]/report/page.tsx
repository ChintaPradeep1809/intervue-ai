"use client";

import type { InterviewPlan, InterviewSummary, Report } from "@intervue/types";
import { Code2, Loader2, MessageSquareText, PlusCircle, Printer } from "lucide-react";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { ReportView } from "@/components/reports/report-view";
import { TranscriptView } from "@/components/reports/transcript-view";
import { ErrorState, LinkButton, LoadingBlock, PageHeader } from "@/components/shared/primitives";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useSession } from "@/lib/session";
import { useApi } from "@/lib/use-api";

interface ReportResponse {
  interview: InterviewSummary;
  plan: InterviewPlan;
  report: Report;
}

export default function ReportPage() {
  const { id } = useParams<{ id: string }>();
  const { user } = useSession();
  const { data, error, loading, reload } = useApi<ReportResponse>(`/interviews/${id}/report`);
  const [tab, setTab] = useState("report");

  // the report may still be generating right after the interview ends
  useEffect(() => {
    if (error?.status !== 409) return;
    const t = setTimeout(reload, 2500);
    return () => clearTimeout(t);
  }, [error, reload]);

  if (loading && !data) return <LoadingBlock rows={5} />;
  if (error?.status === 409)
    return (
      <div className="flex flex-col items-center gap-3 py-24 text-center">
        <Loader2 className="size-8 animate-spin text-primary" />
        <p className="font-medium">Generating your report…</p>
        <p className="text-sm text-muted-foreground">This usually takes a few seconds.</p>
      </div>
    );
  if (error || !data) return <ErrorState message={error?.message ?? "Report not found."} onRetry={reload} />;
  const hasCoding = data.report.coding_summary.length > 0;

  return (
    <>
      <PageHeader
        eyebrow="Interview report"
        title={data.interview.title}
        actions={
          <div className="flex gap-2 print:hidden">
            {hasCoding && (
              <LinkButton href={`/interviews/${id}/coding`} variant="outline" className="h-9">
                <Code2 className="size-4" /> Code
              </LinkButton>
            )}
            <Button variant="outline" className="h-9" onClick={() => window.print()}>
              <Printer className="size-4" /> Export PDF
            </Button>
            <LinkButton href={user?.is_demo ? "/auth/register" : "/interviews/new"} className="h-9">
              <PlusCircle className="size-4" /> {user?.is_demo ? "Create your full interview" : "Practice again"}
            </LinkButton>
          </div>
        }
      />
      {user?.is_demo && (
        <div className="mb-6 rounded-xl border border-primary/30 bg-accent p-4 text-sm text-accent-foreground print:hidden">
          This is a short demo evaluation. Create a free account to get a full, personalised interview based on your own resume and target job.
        </div>
      )}
      <Tabs value={tab} onValueChange={(v) => setTab(String(v))}>
        <TabsList className="print:hidden">
          <TabsTrigger value="report">Report</TabsTrigger>
          <TabsTrigger value="transcript">
            <MessageSquareText className="size-4" /> Transcript
          </TabsTrigger>
        </TabsList>
        <TabsContent value="report" className="pt-4">
          <ReportView report={data.report} interview={data.interview} plan={data.plan} />
        </TabsContent>
        <TabsContent value="transcript" className="pt-4">
          {tab === "transcript" && <TranscriptView interviewId={id} />}
        </TabsContent>
      </Tabs>
    </>
  );
}
