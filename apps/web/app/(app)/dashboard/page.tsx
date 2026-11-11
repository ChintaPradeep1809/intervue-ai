"use client";

import type { InterviewSummary, Report } from "@intervue/types";
import { Award, CheckCircle2, PlusCircle, Target, TrendingUp } from "lucide-react";

import { InterviewList } from "@/components/interview/interview-list";
import { EmptyState, ErrorState, LinkButton, LoadingBlock, PageHeader, ScoreBar, StatCard } from "@/components/shared/primitives";
import { useSession } from "@/lib/session";
import { useApi } from "@/lib/use-api";

export default function DashboardPage() {
  const { user } = useSession();
  const { data, error, loading, reload, setData } = useApi<{ items: InterviewSummary[] }>("/interviews");
  const items = data?.items ?? [];
  const completed = items.filter((i) => i.status === "completed" && i.overall_score !== null);
  const latest = completed[0];
  const { data: latestReport } = useApi<{ report: Report }>(latest ? `/interviews/${latest.id}/report` : null);
  const scores = completed.map((i) => i.overall_score as number);
  const avg = scores.length ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length) : null;
  const upcoming = items.filter((i) => i.status === "planned" || i.status === "in_progress");

  return (
    <>
      <PageHeader
        eyebrow="Dashboard"
        title={`Welcome${user ? `, ${user.full_name.split(" ")[0]}` : ""}`}
        description="Practise, review the evidence, and focus on what moves your score."
        actions={
          <LinkButton href="/interviews/new" className="h-9">
            <PlusCircle className="size-4" /> New interview
          </LinkButton>
        }
      />
      {loading ? (
        <LoadingBlock rows={4} />
      ) : error ? (
        <ErrorState message={error.message} onRetry={reload} />
      ) : items.length === 0 ? (
        <EmptyState
          icon={Target}
          title="No interviews yet"
          description="Create your first personalised interview — it takes about two minutes to set up."
          action={<LinkButton href="/interviews/new">Create interview</LinkButton>}
        />
      ) : (
        <div className="space-y-8">
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard label="Interviews completed" value={completed.length} icon={CheckCircle2} />
            <StatCard label="Average score" value={avg ?? "—"} icon={TrendingUp} />
            <StatCard label="Best score" value={scores.length ? Math.max(...scores) : "—"} icon={Award} />
            <StatCard label="Latest score" value={latest?.overall_score ?? "—"} hint={latest ? latest.role_title : undefined} icon={Target} />
          </div>

          {latestReport && (
            <section className="grid gap-4 md:grid-cols-3">
              <div className="rounded-xl border bg-card p-5 md:col-span-2">
                <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">Latest feedback</p>
                <p className="mt-2 font-medium">{latestReport.report.narrative.headline}</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  {latestReport.report.narrative.strongest_area} {latestReport.report.narrative.main_weakness}
                </p>
                <div className="mt-4 grid gap-3 sm:grid-cols-2">
                  {latestReport.report.topic_scores.slice(0, 6).map((t) => (
                    <div key={t.topic}>
                      <div className="flex justify-between text-sm">
                        <span>{t.label}</span>
                        <span className="tabular text-muted-foreground">{t.score}</span>
                      </div>
                      <ScoreBar score={t.score} className="mt-1" />
                    </div>
                  ))}
                </div>
              </div>
              <div className="rounded-xl border bg-card p-5">
                <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">Recommended next topics</p>
                {latestReport.report.recommended_topics.length ? (
                  <ol className="mt-3 space-y-2 text-sm">
                    {latestReport.report.recommended_topics.slice(0, 5).map((t, i) => (
                      <li key={t} className="flex gap-2">
                        <span className="text-muted-foreground tabular">{i + 1}.</span> {t[0].toUpperCase() + t.slice(1)}
                      </li>
                    ))}
                  </ol>
                ) : (
                  <p className="mt-3 text-sm text-muted-foreground">No gaps detected in your last interview.</p>
                )}
                <LinkButton href={`/interviews/${latest.id}/report`} variant="outline" size="sm" className="mt-4">
                  Open full report
                </LinkButton>
              </div>
            </section>
          )}

          {upcoming.length > 0 && (
            <section>
              <h2 className="mb-3 text-sm font-medium">Ready to start</h2>
              <InterviewList items={upcoming} />
            </section>
          )}
          <section>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-medium">Recent interviews</h2>
              <LinkButton href="/interviews" variant="ghost" size="sm">
                View all
              </LinkButton>
            </div>
            <InterviewList
              items={items.filter((i) => !upcoming.includes(i)).slice(0, 5)}
              onDeleted={(id) => setData({ items: items.filter((i) => i.id !== id) })}
            />
          </section>
        </div>
      )}
    </>
  );
}
