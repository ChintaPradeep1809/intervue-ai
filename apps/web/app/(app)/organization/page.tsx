"use client";

import { Award, CheckCircle2, Gauge, Percent, Target, TrendingUp, Users } from "lucide-react";
import Link from "next/link";

import { CountBars, TrendArea } from "@/components/dashboard/charts";
import { OrgGate } from "@/components/admin/org-gate";
import { EmptyState, ErrorState, LinkButton, LoadingBlock, PageHeader, ScoreBar, ScoreText, StatCard } from "@/components/shared/primitives";
import { formatDate } from "@/lib/format";
import { useApi } from "@/lib/use-api";

interface Dashboard {
  organization: { id: string; name: string; kind: string };
  stats: {
    total_candidates: number;
    interviews_total: number;
    interviews_completed: number;
    average_score: number | null;
    pass_rate: number | null;
    average_technical_score: number | null;
    completion_rate: number | null;
    pass_threshold: number;
  };
  top_skills: { topic: string; label: string; avg_score: number; answers: number }[];
  weakest_skills: { topic: string; label: string; avg_score: number; answers: number }[];
  score_distribution: { range: string; count: number }[];
  completions_by_day: { date: string; count: number }[];
  recent: { interview_id: string; candidate: string; role: string; score: number; completed_at: string }[];
}

export default function OrganizationPage() {
  return (
    <OrgGate>
      <OrgDashboard />
    </OrgGate>
  );
}

function OrgDashboard() {
  const { data, error, loading, reload } = useApi<Dashboard>("/organization");
  if (loading) return <LoadingBlock rows={4} />;
  if (error || !data) return <ErrorState message={error?.message ?? "Could not load the dashboard."} onRetry={reload} />;
  const s = data.stats;
  return (
    <>
      <PageHeader
        eyebrow={data.organization.kind}
        title={data.organization.name}
        description="Cohort performance across all interviews run through your templates and invite links."
        actions={
          <>
            <LinkButton href="/organization/interviews" variant="outline" className="h-9">
              Templates & links
            </LinkButton>
            <LinkButton href="/organization/candidates" className="h-9">
              View candidates
            </LinkButton>
          </>
        }
      />
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Total candidates" value={s.total_candidates} icon={Users} />
        <StatCard label="Interviews completed" value={s.interviews_completed} hint={`${s.interviews_total} total`} icon={CheckCircle2} />
        <StatCard label="Average score" value={s.average_score ?? "—"} icon={Gauge} />
        <StatCard label="Pass rate" value={s.pass_rate !== null ? `${s.pass_rate}%` : "—"} hint={`Threshold ${s.pass_threshold}`} icon={Percent} />
        <StatCard label="Avg technical score" value={s.average_technical_score ?? "—"} icon={TrendingUp} />
        <StatCard label="Completion rate" value={s.completion_rate !== null ? `${s.completion_rate}%` : "—"} icon={Target} />
        <StatCard label="Top skill" value={<span className="text-lg">{data.top_skills[0]?.label ?? "—"}</span>} icon={Award} />
        <StatCard label="Weakest skill" value={<span className="text-lg">{data.weakest_skills[0]?.label ?? "—"}</span>} icon={Target} />
      </div>

      {s.interviews_total === 0 ? (
        <div className="mt-8">
          <EmptyState title="No interviews yet" description="Create a template, generate an invite link and share it with candidates." action={<LinkButton href="/organization/interviews">Create a template</LinkButton>} />
        </div>
      ) : (
        <div className="mt-8 grid gap-6 lg:grid-cols-2">
          <section className="rounded-xl border bg-card p-5">
            <h2 className="mb-2 text-sm font-medium">Completed interviews (last 14 days)</h2>
            <TrendArea data={data.completions_by_day.map((d) => ({ ...d, label: formatDate(d.date, { month: "short", day: "numeric" }) }))} xKey="label" yKey="count" />
          </section>
          <section className="rounded-xl border bg-card p-5">
            <h2 className="mb-2 text-sm font-medium">Score distribution</h2>
            <CountBars data={data.score_distribution} xKey="range" yKey="count" />
          </section>
          <section className="rounded-xl border bg-card p-5">
            <h2 className="mb-3 text-sm font-medium">Strongest skills</h2>
            <SkillList items={data.top_skills} />
          </section>
          <section className="rounded-xl border bg-card p-5">
            <h2 className="mb-3 text-sm font-medium">Lowest-scoring skills</h2>
            <SkillList items={data.weakest_skills} />
          </section>
          <section className="rounded-xl border bg-card p-5 lg:col-span-2">
            <h2 className="mb-3 text-sm font-medium">Recently completed</h2>
            <ul className="divide-y">
              {data.recent.map((r) => (
                <li key={r.interview_id} className="flex items-center gap-3 py-2.5 text-sm">
                  <Link href={`/interviews/${r.interview_id}/report`} className="flex-1 font-medium hover:underline">
                    {r.candidate}
                  </Link>
                  <span className="hidden text-muted-foreground sm:inline">{r.role}</span>
                  <span className="text-xs text-muted-foreground">{formatDate(r.completed_at)}</span>
                  <ScoreText score={r.score} className="w-8 text-right" />
                </li>
              ))}
            </ul>
          </section>
        </div>
      )}
    </>
  );
}

function SkillList({ items }: { items: { topic: string; label: string; avg_score: number; answers: number }[] }) {
  if (!items.length) return <p className="text-sm text-muted-foreground">No data yet.</p>;
  return (
    <ul className="space-y-2.5">
      {items.map((t) => (
        <li key={t.topic}>
          <div className="flex justify-between text-sm">
            <span>{t.label}</span>
            <span className="text-muted-foreground tabular">
              {t.avg_score} · {t.answers} answers
            </span>
          </div>
          <ScoreBar score={t.avg_score} className="mt-1" />
        </li>
      ))}
    </ul>
  );
}
