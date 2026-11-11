"use client";

import { Download, X } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { CountBars } from "@/components/dashboard/charts";
import { OrgGate } from "@/components/admin/org-gate";
import { EmptyState, ErrorState, LoadingBlock, PageHeader, ScoreBar, ScoreText } from "@/components/shared/primitives";
import { Button } from "@/components/ui/button";
import { titleCase } from "@/lib/format";
import { useApi } from "@/lib/use-api";

interface Aggregate {
  reports: number;
  category_averages: { category: string; score: number }[];
  section_averages: { category: string; score: number }[];
  readiness: { label: string; count: number }[];
  common_gaps: { concept: string; count: number }[];
  by_role: { role: string; average: number; count: number }[];
}
interface CompareItem {
  interview_id: string;
  candidate_name: string;
  role: string;
  score: number | null;
  section_scores: { category: string; score: number }[];
  category_scores: { category: string; score: number }[];
  topic_scores: { topic: string; label: string; score: number }[];
  strong_areas: string[];
  weak_areas: string[];
  readiness: string;
}

export default function OrgReportsPage() {
  return (
    <OrgGate>
      <Suspense fallback={<LoadingBlock rows={3} />}>
        <Reports />
      </Suspense>
    </OrgGate>
  );
}

function Reports() {
  const params = useSearchParams();
  const compare = params.get("compare");
  return (
    <>
      <PageHeader
        title="Reports"
        description="Aggregate performance across your cohort, and side-by-side candidate comparison."
        actions={
          <a href="/api/organization/export.csv" className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-primary px-3 text-sm font-medium text-primary-foreground hover:bg-primary/90">
            <Download className="size-4" /> Export CSV
          </a>
        }
      />
      {compare && <Compare ids={compare} />}
      <AggregateView />
    </>
  );
}

function Compare({ ids }: { ids: string }) {
  const router = useRouter();
  const { data, error, loading } = useApi<{ items: CompareItem[] }>(`/organization/compare?ids=${ids}`);
  if (loading) return <LoadingBlock rows={2} />;
  if (error) return <ErrorState message={error.message} />;
  const items = data?.items ?? [];
  const cats = Array.from(new Set(items.flatMap((i) => i.section_scores.map((s) => s.category))));
  const topics = Array.from(new Set(items.flatMap((i) => i.topic_scores.map((s) => s.label))));
  return (
    <section className="mb-10 rounded-xl border bg-card" aria-label="Candidate comparison">
      <div className="flex items-center justify-between border-b px-4 py-3">
        <h2 className="text-sm font-medium">Comparing {items.length} candidates</h2>
        <Button variant="ghost" size="sm" onClick={() => router.replace("/organization/reports")}>
          <X className="size-4" /> Close
        </Button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b">
              <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground">Metric</th>
              {items.map((i) => (
                <th key={i.interview_id} className="px-4 py-3 text-left">
                  <Link href={`/interviews/${i.interview_id}/report`} className="font-medium hover:underline">{i.candidate_name}</Link>
                  <p className="text-xs font-normal text-muted-foreground">{i.readiness}</p>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr className="border-b bg-muted/30">
              <td className="px-4 py-2 font-medium">Overall</td>
              {items.map((i) => <td key={i.interview_id} className="px-4 py-2"><ScoreText score={i.score} className="text-base" /></td>)}
            </tr>
            {cats.map((c) => (
              <tr key={c} className="border-b">
                <td className="px-4 py-2 text-muted-foreground">{titleCase(c)}</td>
                {items.map((i) => {
                  const s = i.section_scores.find((x) => x.category === c)?.score ?? null;
                  return <td key={i.interview_id} className="px-4 py-2"><div className="flex items-center gap-2"><ScoreText score={s} className="w-8" /><ScoreBar score={s} className="max-w-28" /></div></td>;
                })}
              </tr>
            ))}
            {topics.map((t) => (
              <tr key={t} className="border-b">
                <td className="px-4 py-2 text-muted-foreground">{t}</td>
                {items.map((i) => <td key={i.interview_id} className="px-4 py-2"><ScoreText score={i.topic_scores.find((x) => x.label === t)?.score ?? null} /></td>)}
              </tr>
            ))}
            <tr className="border-b">
              <td className="px-4 py-2 text-muted-foreground">Strong areas</td>
              {items.map((i) => <td key={i.interview_id} className="px-4 py-2 text-xs">{i.strong_areas.join(", ") || "—"}</td>)}
            </tr>
            <tr>
              <td className="px-4 py-2 text-muted-foreground">Weak areas</td>
              {items.map((i) => <td key={i.interview_id} className="px-4 py-2 text-xs">{i.weak_areas.join(", ") || "—"}</td>)}
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  );
}

function AggregateView() {
  const { data, error, loading, reload } = useApi<Aggregate>("/organization/reports");
  if (loading) return <LoadingBlock rows={3} />;
  if (error || !data) return <ErrorState message={error?.message ?? "Could not load reports."} onRetry={reload} />;
  if (!data.reports) return <EmptyState title="No completed reports yet" description="Aggregates appear once candidates finish their interviews." />;
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <section className="rounded-xl border bg-card p-5">
        <h2 className="mb-3 text-sm font-medium">Average by section</h2>
        <ul className="space-y-2.5">
          {data.section_averages.map((s) => (
            <li key={s.category}>
              <div className="flex justify-between text-sm"><span>{titleCase(s.category)}</span><ScoreText score={s.score} /></div>
              <ScoreBar score={s.score} className="mt-1" />
            </li>
          ))}
        </ul>
      </section>
      <section className="rounded-xl border bg-card p-5">
        <h2 className="mb-3 text-sm font-medium">Average by evaluation category</h2>
        <ul className="space-y-2.5">
          {data.category_averages.map((s) => (
            <li key={s.category}>
              <div className="flex justify-between text-sm"><span>{titleCase(s.category)}</span><ScoreText score={s.score} /></div>
              <ScoreBar score={s.score} className="mt-1" />
            </li>
          ))}
        </ul>
      </section>
      <section className="rounded-xl border bg-card p-5">
        <h2 className="mb-2 text-sm font-medium">Readiness</h2>
        <CountBars data={data.readiness} xKey="label" yKey="count" />
      </section>
      <section className="rounded-xl border bg-card p-5">
        <h2 className="mb-3 text-sm font-medium">Most common gaps across the cohort</h2>
        {data.common_gaps.length ? (
          <ol className="space-y-1.5 text-sm">
            {data.common_gaps.map((g, i) => (
              <li key={g.concept} className="flex justify-between">
                <span><span className="mr-2 text-muted-foreground tabular">{i + 1}.</span>{g.concept}</span>
                <span className="text-muted-foreground tabular">{g.count} candidates</span>
              </li>
            ))}
          </ol>
        ) : (
          <p className="text-sm text-muted-foreground">No recurring gaps.</p>
        )}
      </section>
      <section className="rounded-xl border bg-card p-5 lg:col-span-2">
        <h2 className="mb-3 text-sm font-medium">By role</h2>
        <ul className="divide-y text-sm">
          {data.by_role.map((r) => (
            <li key={r.role} className="flex justify-between py-2">
              <span>{r.role}</span>
              <span className="text-muted-foreground">{r.count} reports · avg <ScoreText score={r.average} /></span>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
