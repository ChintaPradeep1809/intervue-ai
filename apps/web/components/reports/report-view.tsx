"use client";

import type { Evidence, InterviewPlan, InterviewSummary, Report } from "@intervue/types";
import { CheckCircle2, ChevronDown, Code2, FileText, MinusCircle, Quote, Ruler, Target, TrendingDown, TrendingUp } from "lucide-react";
import { useState } from "react";

import { ScoreBar, ScoreRing, ScoreText } from "@/components/shared/primitives";
import { formatDateTime, titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";

const CATEGORY_LABEL: Record<string, string> = {
  technical_correctness: "Technical correctness",
  problem_solving: "Problem solving",
  communication: "Communication",
  code_quality: "Code quality",
  architecture: "Architecture",
  tradeoffs: "Trade-offs",
  debugging: "Debugging",
  depth_of_knowledge: "Depth of knowledge",
  time_management: "Time management",
};
const SECTION_LABEL: Record<string, string> = {
  technical: "Technical",
  communication: "Communication",
  problem_solving: "Problem solving",
  coding: "Coding",
  system_design: "System design",
};
const SOURCE_ICON: Record<Evidence["source"], React.ComponentType<{ className?: string }>> = {
  transcript: Quote,
  code: Code2,
  execution: Ruler,
  design: FileText,
};

function EvidenceItem({ e }: { e: Evidence }) {
  const Icon = SOURCE_ICON[e.source];
  return (
    <li className="flex gap-2.5 text-sm">
      {e.polarity === "positive" ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" /> : <MinusCircle className="mt-0.5 size-4 shrink-0 text-destructive" />}
      <div className="min-w-0">
        <p>{e.observation}</p>
        {e.kind === "quote" && e.quote && (
          <blockquote className="mt-1 flex gap-1.5 border-l-2 pl-2.5 text-xs text-muted-foreground italic">
            <Icon className="mt-0.5 size-3 shrink-0 not-italic" />
            <span className="break-words">“{e.quote}”</span>
          </blockquote>
        )}
      </div>
    </li>
  );
}

export function ReportView({ report, interview, plan }: { report: Report; interview: InterviewSummary; plan: InterviewPlan }) {
  const [open, setOpen] = useState<string | null>(null);
  const [openQ, setOpenQ] = useState<number | null>(null);
  return (
    <div className="space-y-8">
      {/* Summary */}
      <section className="grid gap-6 rounded-2xl border bg-card p-6 md:grid-cols-[auto_1fr]">
        <div className="flex flex-col items-center gap-2">
          <ScoreRing score={report.overall_score} size={136} label="Overall" />
          <span className={cn("rounded-full px-2.5 py-0.5 text-xs font-medium", report.role_readiness === "ready" ? "bg-success/15 text-success" : report.role_readiness === "nearly_ready" ? "bg-accent text-accent-foreground" : "bg-muted text-muted-foreground")}>
            {report.readiness_label}
          </span>
        </div>
        <div className="space-y-3">
          <div>
            <p className="text-xs text-muted-foreground">
              {plan.role_title} · {formatDateTime(interview.completed_at)} · {report.answered_count} answers
            </p>
            <h2 className="mt-1 text-xl font-semibold">{report.narrative.headline}</h2>
          </div>
          <p className="text-sm text-muted-foreground">{report.narrative.summary}</p>
          <div className="grid gap-2 sm:grid-cols-2">
            <p className="flex gap-2 rounded-lg bg-success/10 p-3 text-sm">
              <TrendingUp className="mt-0.5 size-4 shrink-0 text-success" /> {report.narrative.strongest_area}
            </p>
            <p className="flex gap-2 rounded-lg bg-destructive/5 p-3 text-sm">
              <TrendingDown className="mt-0.5 size-4 shrink-0 text-destructive" /> {report.narrative.main_weakness}
            </p>
          </div>
        </div>
      </section>

      {/* Section scores */}
      {report.section_scores.length > 0 && (
        <section className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          {report.section_scores.map((s) => (
            <div key={s.category} className="flex flex-col items-center rounded-xl border bg-card p-4">
              <ScoreRing score={s.score} size={84} />
              <p className="mt-2 text-sm font-medium">{SECTION_LABEL[s.category] ?? titleCase(s.category)}</p>
            </div>
          ))}
        </section>
      )}

      <div className="grid gap-6 lg:grid-cols-[1.3fr_1fr]">
        {/* Categories with evidence */}
        <section aria-labelledby="cat-h" className="space-y-3">
          <h2 id="cat-h" className="font-semibold">Evaluation by category</h2>
          <p className="text-xs text-muted-foreground">Every observation is grounded in your transcript, code or test results. Quotes that couldn&apos;t be verified were discarded.</p>
          <ul className="divide-y rounded-xl border bg-card">
            {report.category_scores.map((c) => {
              const ev = report.category_evidence[c.category] ?? [];
              const isOpen = open === c.category;
              return (
                <li key={c.category}>
                  <button className="flex w-full items-center gap-3 px-4 py-3 text-left" aria-expanded={isOpen} onClick={() => setOpen(isOpen ? null : c.category)}>
                    <span className="w-44 shrink-0 text-sm font-medium">{CATEGORY_LABEL[c.category] ?? titleCase(c.category)}</span>
                    <ScoreBar score={c.score} className="flex-1" />
                    <ScoreText score={c.score} className="w-8 text-right text-sm" />
                    <ChevronDown className={cn("size-4 shrink-0 text-muted-foreground transition-transform", isOpen && "rotate-180")} />
                  </button>
                  {isOpen && (
                    <div className="px-4 pb-4">
                      {ev.length ? <ul className="space-y-3">{ev.map((e, i) => <EvidenceItem key={i} e={e} />)}</ul> : <p className="text-sm text-muted-foreground">No specific evidence recorded for this category.</p>}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </section>

        <div className="space-y-6">
          <section aria-labelledby="topics-h" className="rounded-xl border bg-card p-5">
            <h2 id="topics-h" className="mb-3 font-semibold">Topics</h2>
            <ul className="space-y-2.5">
              {report.topic_scores.map((t) => (
                <li key={t.topic}>
                  <div className="flex justify-between text-sm">
                    <span>{t.label}</span>
                    <ScoreText score={t.score} />
                  </div>
                  <ScoreBar score={t.score} className="mt-1" />
                </li>
              ))}
            </ul>
            <div className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
              <div>
                <p className="mb-1.5 text-xs font-medium text-muted-foreground uppercase">Strong areas</p>
                {report.strong_areas.length ? report.strong_areas.map((s) => <p key={s}>• {s}</p>) : <p className="text-muted-foreground">—</p>}
              </div>
              <div>
                <p className="mb-1.5 text-xs font-medium text-muted-foreground uppercase">Weak areas</p>
                {report.weak_areas.length ? report.weak_areas.map((s) => <p key={s}>• {s}</p>) : <p className="text-muted-foreground">—</p>}
              </div>
            </div>
          </section>

          <section aria-labelledby="rec-h" className="rounded-xl border bg-card p-5">
            <h2 id="rec-h" className="mb-3 flex items-center gap-2 font-semibold">
              <Target className="size-4 text-primary" /> Recommended next topics
            </h2>
            {report.recommended_topics.length ? (
              <ol className="space-y-1.5 text-sm">
                {report.recommended_topics.map((t, i) => (
                  <li key={t}>
                    <span className="mr-2 text-muted-foreground tabular">{i + 1}.</span>
                    {t[0].toUpperCase() + t.slice(1)}
                  </li>
                ))}
              </ol>
            ) : (
              <p className="text-sm text-muted-foreground">No major gaps were detected.</p>
            )}
          </section>
        </div>
      </div>

      {/* Practice plan */}
      {report.practice_plan.length > 0 && (
        <section aria-labelledby="plan-h">
          <h2 id="plan-h" className="mb-3 font-semibold">Suggested practice plan</h2>
          <ol className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
            {report.practice_plan.map((p) => (
              <li key={p.day} className="rounded-xl border bg-card p-4">
                <p className="text-xs font-medium text-primary">{p.day}</p>
                <p className="mt-1 font-medium">{p.focus}</p>
                <ul className="mt-2 space-y-1 text-sm text-muted-foreground">
                  {p.activities.map((a) => (
                    <li key={a}>• {a}</li>
                  ))}
                </ul>
              </li>
            ))}
          </ol>
        </section>
      )}

      {/* Coding */}
      {report.coding_summary.length > 0 && (
        <section aria-labelledby="code-h">
          <h2 id="code-h" className="mb-3 font-semibold">Coding performance</h2>
          <div className="overflow-x-auto rounded-xl border bg-card">
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-muted-foreground">
                <tr className="border-b">
                  <th className="px-4 py-2 font-medium">Problem</th>
                  <th className="px-4 py-2 font-medium">Language</th>
                  <th className="px-4 py-2 font-medium">Tests</th>
                  <th className="px-4 py-2 font-medium">Runs</th>
                  <th className="px-4 py-2 font-medium">Runtime</th>
                </tr>
              </thead>
              <tbody>
                {report.coding_summary.map((c, i) => (
                  <tr key={i} className="border-b last:border-0">
                    <td className="px-4 py-2">{c.problem}</td>
                    <td className="px-4 py-2">{c.language}</td>
                    <td className="px-4 py-2">
                      <span className={c.passed === c.total ? "text-success" : "text-destructive"}>
                        {c.passed}/{c.total}
                      </span>
                    </td>
                    <td className="px-4 py-2 tabular">{c.runs}</td>
                    <td className="px-4 py-2 tabular">{c.runtime_ms} ms</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Question analysis */}
      <section aria-labelledby="qa-h">
        <h2 id="qa-h" className="mb-3 font-semibold">Question-by-question analysis</h2>
        <ul className="divide-y rounded-xl border bg-card">
          {report.question_analysis.map((q, i) => (
            <li key={i}>
              <button className="flex w-full items-start gap-3 px-4 py-3 text-left" aria-expanded={openQ === i} onClick={() => setOpenQ(openQ === i ? null : i)}>
                <ScoreText score={q.score} className="w-8 shrink-0 text-sm" />
                <div className="min-w-0 flex-1">
                  <p className="text-sm">{q.question}</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {q.topic} · {q.kind.replace("_", " ")}
                  </p>
                </div>
                <ChevronDown className={cn("mt-1 size-4 shrink-0 text-muted-foreground transition-transform", openQ === i && "rotate-180")} />
              </button>
              {openQ === i && (
                <div className="space-y-2 px-4 pb-4 pl-15 text-sm">
                  <p className="text-muted-foreground">{q.summary}</p>
                  {q.covered.length > 0 && <p><span className="text-success">Covered:</span> {q.covered.join(", ")}</p>}
                  {q.missing.length > 0 && <p><span className="text-destructive">Missed:</span> {q.missing.join(", ")}</p>}
                </div>
              )}
            </li>
          ))}
        </ul>
      </section>

      <p className="text-xs text-muted-foreground">{report.disclaimer}</p>
    </div>
  );
}
