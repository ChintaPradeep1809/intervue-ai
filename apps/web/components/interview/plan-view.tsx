import { ROUND_KIND_LABELS } from "@intervue/config";
import type { InterviewPlan, ResumeAnalysis } from "@intervue/types";
import { AlertCircle, Brain, Clock, Code2, Database, ListChecks, MessageSquare, Network, Sparkles, UserRound } from "lucide-react";

import { cn } from "@/lib/utils";

const KIND_ICON: Record<string, React.ComponentType<{ className?: string }>> = {
  introduction: UserRound,
  technical: Brain,
  coding: Code2,
  sql: Database,
  system_design: Network,
  behavioral: MessageSquare,
};

export function PlanView({ plan, analysis, compact }: { plan: InterviewPlan; analysis?: ResumeAnalysis; compact?: boolean }) {
  const maxW = Math.max(...plan.skill_weights.map((w) => w.weight), 0.01);
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-3 gap-3">
        {[
          { icon: Clock, label: "Duration", value: `${plan.duration_minutes} min` },
          { icon: ListChecks, label: "Questions", value: `~${plan.total_questions}` },
          { icon: Sparkles, label: "Difficulty", value: plan.difficulty.replace(/^\w/, (c) => c.toUpperCase()) },
        ].map((s) => (
          <div key={s.label} className="rounded-xl border bg-card p-3">
            <s.icon className="size-4 text-muted-foreground" />
            <div className="mt-2 text-lg font-semibold">{s.value}</div>
            <div className="text-xs text-muted-foreground">{s.label}</div>
          </div>
        ))}
      </div>

      <div className={cn("grid gap-6", !compact && "md:grid-cols-2")}>
        <section aria-labelledby="rounds-h">
          <h3 id="rounds-h" className="mb-3 text-sm font-medium">Round structure</h3>
          <ol className="relative space-y-2">
            {plan.rounds.map((r, i) => {
              const Icon = KIND_ICON[r.kind] ?? Brain;
              return (
                <li key={r.id} className="flex items-center gap-3 rounded-lg border bg-card px-3 py-2.5">
                  <span className="grid size-8 shrink-0 place-items-center rounded-md bg-accent text-accent-foreground">
                    <Icon className="size-4" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">
                      {i + 1}. {r.title}
                    </p>
                    <p className="truncate text-xs text-muted-foreground">
                      {ROUND_KIND_LABELS[r.kind]}
                      {r.kind === "technical" || r.kind === "behavioral" ? ` · ${r.question_count} questions` : ""}
                      {r.language ? ` · ${r.language === "sql" ? "SQL" : r.language}` : ""}
                    </p>
                  </div>
                  <span className="text-xs text-muted-foreground tabular">{r.minutes} min</span>
                </li>
              );
            })}
          </ol>
        </section>

        <section aria-labelledby="skills-h">
          <h3 id="skills-h" className="mb-3 text-sm font-medium">Skills being tested</h3>
          <ul className="space-y-2.5">
            {plan.skill_weights.slice(0, 10).map((w) => (
              <li key={w.topic}>
                <div className="flex justify-between text-sm">
                  <span>{w.label}</span>
                  <span className="text-muted-foreground tabular">{Math.round(w.weight * 100)}%</span>
                </div>
                <div className="mt-1 h-1.5 rounded-full bg-muted">
                  <div className="h-full rounded-full bg-primary" style={{ width: `${(w.weight / maxW) * 100}%` }} />
                </div>
              </li>
            ))}
          </ul>
        </section>
      </div>

      {(plan.rationale.length > 0 || analysis) && (
        <section className="rounded-xl border bg-muted/40 p-4 text-sm">
          <h3 className="mb-2 font-medium">Why this plan</h3>
          <ul className="space-y-1.5 text-muted-foreground">
            {plan.rationale.map((r) => (
              <li key={r}>• {r}</li>
            ))}
            {analysis?.notes.map((n) => (
              <li key={n} className="flex gap-1.5">
                <AlertCircle className="mt-0.5 size-3.5 shrink-0" /> {n}
              </li>
            ))}
          </ul>
          {analysis && analysis.skills.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {analysis.skills.slice(0, 14).map((s) => (
                <span key={s.name} title={`From your resume: “${s.evidence}”`} className="rounded-full border bg-background px-2 py-0.5 text-xs">
                  {s.name}
                </span>
              ))}
            </div>
          )}
        </section>
      )}
    </div>
  );
}
