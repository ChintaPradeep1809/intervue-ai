"use client";

import type { InterviewSummary } from "@intervue/types";
import { History } from "lucide-react";

import { ScoreTrend } from "@/components/dashboard/charts";
import { InterviewList } from "@/components/interview/interview-list";
import { EmptyState, ErrorState, LinkButton, LoadingBlock, PageHeader, StatCard } from "@/components/shared/primitives";
import { formatDate } from "@/lib/format";
import { useApi } from "@/lib/use-api";

export default function HistoryPage() {
  const { data, error, loading, reload, setData } = useApi<{ items: InterviewSummary[] }>("/interviews?limit=100");
  const completed = (data?.items ?? []).filter((i) => i.status === "completed" && i.overall_score !== null);
  const chronological = [...completed].reverse();
  const first = chronological[0]?.overall_score ?? null;
  const last = chronological.at(-1)?.overall_score ?? null;
  return (
    <>
      <PageHeader title="Progress" description="How your scores have changed across completed interviews." />
      {loading ? (
        <LoadingBlock rows={3} />
      ) : error ? (
        <ErrorState message={error.message} onRetry={reload} />
      ) : completed.length === 0 ? (
        <EmptyState icon={History} title="No completed interviews yet" description="Finish an interview to start tracking your progress." action={<LinkButton href="/interviews/new">Start an interview</LinkButton>} />
      ) : (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard label="Completed" value={completed.length} />
            <StatCard label="First score" value={first ?? "—"} />
            <StatCard label="Latest score" value={last ?? "—"} />
            <StatCard label="Change" value={first !== null && last !== null ? `${last - first >= 0 ? "+" : ""}${last - first}` : "—"} />
          </div>
          <section className="rounded-xl border bg-card p-5">
            <h2 className="mb-2 text-sm font-medium">Overall score over time</h2>
            <ScoreTrend data={chronological.map((i) => ({ label: formatDate(i.completed_at, { month: "short", day: "numeric" }), score: i.overall_score as number }))} />
          </section>
          <InterviewList items={completed} onDeleted={(id) => setData({ items: (data?.items ?? []).filter((i) => i.id !== id) })} />
        </div>
      )}
    </>
  );
}
