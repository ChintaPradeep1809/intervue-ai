"use client";

import type { Report } from "@intervue/types";
import { FileText } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { OrgGate } from "@/components/admin/org-gate";
import { TranscriptView } from "@/components/reports/transcript-view";
import { ErrorState, LinkButton, LoadingBlock, NativeSelect, PageHeader, ScoreBar, ScoreRing, ScoreText, StatusBadge } from "@/components/shared/primitives";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { api, errorMessage } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useApi } from "@/lib/use-api";

import type { CandidateRow } from "@/components/admin/types";

interface Detail {
  candidate: { id: string; full_name: string; email: string; experience_years: number | null; headline: string };
  resumes: { id: string; filename: string }[];
  interviews: (CandidateRow & { analysis_skills: string[] })[];
  latest_report: Report | null;
}

export default function CandidateDetailPage() {
  return (
    <OrgGate>
      <CandidateDetail />
    </OrgGate>
  );
}

function ReviewBox({ row, onSaved }: { row: CandidateRow; onSaved: () => void }) {
  const [status, setStatus] = useState(row.review_status);
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <div className="space-y-2 rounded-xl border bg-card p-4">
      <p className="text-sm font-medium">Reviewer decision</p>
      <p className="text-xs text-muted-foreground">The AI assessment supports your decision — it never decides on its own.</p>
      <NativeSelect aria-label="Review status" value={status} onChange={(e) => setStatus(e.target.value)}>
        <option value="pending">Pending</option>
        <option value="shortlisted">Shortlist</option>
        <option value="on_hold">On hold</option>
        <option value="rejected">Not progressing</option>
      </NativeSelect>
      <Textarea aria-label="Reviewer notes" rows={3} placeholder="Notes for your team (optional)" value={notes} onChange={(e) => setNotes(e.target.value)} />
      <Button
        size="sm"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          try {
            await api(`/organization/interviews/${row.interview_id}/review`, { method: "PATCH", body: { review_status: status, notes } });
            toast.success("Review saved");
            onSaved();
          } catch (e) {
            toast.error(errorMessage(e));
          } finally {
            setBusy(false);
          }
        }}
      >
        Save decision
      </Button>
    </div>
  );
}

function CandidateDetail() {
  const { id } = useParams<{ id: string }>();
  const { data, error, loading, reload } = useApi<Detail>(`/organization/candidates/${id}`);
  const [transcriptFor, setTranscriptFor] = useState<string | null>(null);
  if (loading) return <LoadingBlock rows={4} />;
  if (error || !data) return <ErrorState message={error?.message ?? "Candidate not found."} onRetry={reload} />;
  const latest = data.interviews.find((i) => i.status === "completed");
  const r = data.latest_report;

  return (
    <>
      <PageHeader
        eyebrow={<Link href="/organization/candidates" className="hover:underline">Candidates</Link>}
        title={data.candidate.full_name}
        description={`${data.candidate.email}${data.candidate.experience_years !== null ? ` · ${data.candidate.experience_years} yrs experience` : ""}`}
        actions={latest && <LinkButton href={`/interviews/${latest.interview_id}/report`} className="h-9">Open full report</LinkButton>}
      />
      <div className="grid gap-6 lg:grid-cols-[1.5fr_1fr]">
        <div className="space-y-6">
          {r ? (
            <section className="grid gap-5 rounded-xl border bg-card p-5 sm:grid-cols-[auto_1fr]">
              <ScoreRing score={r.overall_score} label="Overall" />
              <div className="space-y-2">
                <p className="font-medium">{r.readiness_label}</p>
                <p className="text-sm text-muted-foreground">{r.narrative.strongest_area} {r.narrative.main_weakness}</p>
                <div className="grid gap-2 pt-2 sm:grid-cols-2">
                  {r.section_scores.map((s) => (
                    <div key={s.category}>
                      <div className="flex justify-between text-xs"><span className="capitalize">{s.category.replace("_", " ")}</span><ScoreText score={s.score} /></div>
                      <ScoreBar score={s.score} className="mt-1" />
                    </div>
                  ))}
                </div>
              </div>
            </section>
          ) : (
            <p className="rounded-xl border p-5 text-sm text-muted-foreground">No completed report yet.</p>
          )}

          <section className="rounded-xl border bg-card">
            <h2 className="border-b px-4 py-3 text-sm font-medium">Interviews</h2>
            <ul className="divide-y">
              {data.interviews.map((i) => (
                <li key={i.interview_id} className="space-y-2 px-4 py-3">
                  <div className="flex flex-wrap items-center gap-3 text-sm">
                    <span className="min-w-0 flex-1 truncate font-medium">{i.interview}</span>
                    <StatusBadge status={i.status} />
                    <StatusBadge status={i.review_status} />
                    <ScoreText score={i.score} />
                    <span className="text-xs text-muted-foreground">{formatDate(i.date)}</span>
                  </div>
                  {i.analysis_skills.length > 0 && <p className="text-xs text-muted-foreground">Resume skills: {i.analysis_skills.join(", ")}</p>}
                  <div className="flex gap-2">
                    {i.status === "completed" && <LinkButton href={`/interviews/${i.interview_id}/report`} variant="outline" size="sm">Report</LinkButton>}
                    {i.status !== "planned" && (
                      <Button variant="ghost" size="sm" onClick={() => setTranscriptFor(transcriptFor === i.interview_id ? null : i.interview_id)}>
                        {transcriptFor === i.interview_id ? "Hide transcript" : "Transcript"}
                      </Button>
                    )}
                  </div>
                  {transcriptFor === i.interview_id && (
                    <div className="max-h-96 overflow-y-auto rounded-lg border p-3">
                      <TranscriptView interviewId={i.interview_id} />
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </section>
        </div>

        <div className="space-y-6">
          {latest && <ReviewBox row={latest} onSaved={reload} />}
          <section className="rounded-xl border bg-card p-4">
            <p className="mb-2 text-sm font-medium">Resume</p>
            {data.resumes.length ? (
              data.resumes.map((res) => (
                <button
                  key={res.id}
                  className="flex items-center gap-2 text-sm hover:underline"
                  onClick={async () => {
                    try {
                      const { url } = await api<{ url: string }>(`/documents/resume/${res.id}/url`);
                      window.open(url, "_blank", "noopener");
                    } catch (e) {
                      toast.error(errorMessage(e));
                    }
                  }}
                >
                  <FileText className="size-4" /> {res.filename}
                </button>
              ))
            ) : (
              <p className="text-sm text-muted-foreground">No resume attached.</p>
            )}
          </section>
          {r && (
            <section className="rounded-xl border bg-card p-4 text-sm">
              <p className="mb-2 font-medium">Strengths & gaps</p>
              <p className="text-xs text-muted-foreground uppercase">Strong</p>
              <p className="mb-2">{r.strong_areas.join(", ") || "—"}</p>
              <p className="text-xs text-muted-foreground uppercase">Weak</p>
              <p className="mb-2">{r.weak_areas.join(", ") || "—"}</p>
              <p className="text-xs text-muted-foreground uppercase">Recommended topics</p>
              <p>{r.recommended_topics.join(", ") || "—"}</p>
            </section>
          )}
        </div>
      </div>
    </>
  );
}
