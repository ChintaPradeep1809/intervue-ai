"use client";

import { INTERVIEW_TYPE_LABELS } from "@intervue/config";
import type { Catalog, InterviewDetail } from "@intervue/types";
import { ArrowLeft, ArrowRight, Check, FileUp, Sparkles, Upload, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { PlanView } from "@/components/interview/plan-view";
import { MockNotice, NativeSelect, Spinner } from "@/components/shared/primitives";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { api, errorMessage } from "@/lib/api";
import { useSession } from "@/lib/session";
import { useApi } from "@/lib/use-api";
import { cn } from "@/lib/utils";

type Step = "profile" | "resume" | "job" | "preferences" | "plan";

interface ProfileData {
  full_name: string;
  email: string;
  experience_years: number | null;
  target_role: string | null;
  resumes: { id: string; filename: string; created_at: string }[];
}

const STEP_LABELS: Record<Step, string> = {
  profile: "About you",
  resume: "Resume",
  job: "Target job",
  preferences: "Preferences",
  plan: "Interview plan",
};

function Dropzone({ accept, onFile, busy, label }: { accept: string; onFile: (f: File) => void; busy: boolean; label: string }) {
  const ref = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        const f = e.dataTransfer.files[0];
        if (f) onFile(f);
      }}
      className={cn("flex flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-10 text-center transition-colors", over ? "border-primary bg-accent" : "border-border")}
    >
      <Upload className="size-6 text-muted-foreground" />
      <p className="mt-3 text-sm font-medium">{label}</p>
      <p className="mt-1 text-xs text-muted-foreground">PDF or DOCX, up to 8 MB. Files are parsed for text, never executed.</p>
      <Button type="button" variant="outline" size="sm" className="mt-4" disabled={busy} onClick={() => ref.current?.click()}>
        {busy ? <Spinner /> : <FileUp className="size-4" />} Choose file
      </Button>
      <input
        ref={ref}
        type="file"
        accept={accept}
        className="sr-only"
        aria-label={label}
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onFile(f);
          e.target.value = "";
        }}
      />
    </div>
  );
}

export function InterviewWizard({ includeProfile }: { includeProfile: boolean }) {
  const router = useRouter();
  const { config, refresh } = useSession();
  const { data: catalog } = useApi<Catalog>("/catalog");
  const { data: profile } = useApi<ProfileData>("/me/profile");
  const steps: Step[] = includeProfile ? ["profile", "resume", "job", "preferences", "plan"] : ["resume", "job", "preferences", "plan"];
  const [step, setStep] = useState<Step>(steps[0]);
  const [name, setName] = useState("");
  const [years, setYears] = useState<string>("");
  const [role, setRole] = useState("aws_data_engineer");
  const [resume, setResume] = useState<{ id: string; filename: string; detected_skills?: string[] } | null>(null);
  const [jdMode, setJdMode] = useState<"role" | "paste" | "upload">("role");
  const [jdText, setJdText] = useState("");
  const [jdTitle, setJdTitle] = useState("");
  const [jd, setJd] = useState<{ id: string; title: string; detected_skills: string[] } | null>(null);
  const [duration, setDuration] = useState(45);
  const [difficulty, setDifficulty] = useState("medium");
  const [itype, setItype] = useState("full");
  const [busy, setBusy] = useState(false);
  const [interview, setInterview] = useState<InterviewDetail | null>(null);

  useEffect(() => {
    if (!profile) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- seed the form once the profile loads
    setName(profile.full_name);
    if (profile.experience_years !== null) setYears(String(profile.experience_years));
    if (profile.target_role) setRole(profile.target_role);
    if (profile.resumes[0]) setResume({ id: profile.resumes[0].id, filename: profile.resumes[0].filename });
  }, [profile]);

  const idx = steps.indexOf(step);
  const go = (d: 1 | -1) => setStep(steps[Math.max(0, Math.min(steps.length - 1, idx + d))]);

  async function saveProfile() {
    setBusy(true);
    try {
      await api("/me/profile", { method: "PUT", body: { full_name: name, experience_years: years === "" ? null : Number(years), target_role: role } });
      go(1);
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  async function uploadResume(f: File) {
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", f);
      const r = await api<{ id: string; filename: string; detected_skills: string[] }>("/documents/resume", { body: fd });
      setResume(r);
      toast.success(`Resume uploaded — ${r.detected_skills.length} skills detected`);
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  async function uploadJd(f: File) {
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", f);
      fd.append("title", jdTitle);
      setJd(await api("/documents/jd/upload", { body: fd }));
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  async function continueFromJob() {
    if (jdMode === "paste" && !jd) {
      if (jdText.trim().length < 20) {
        toast.error("Paste at least a few lines of the job description, or choose a role instead.");
        return;
      }
      setBusy(true);
      try {
        setJd(await api("/documents/jd", { body: { title: jdTitle, text: jdText } }));
      } catch (e) {
        toast.error(errorMessage(e));
        setBusy(false);
        return;
      }
      setBusy(false);
    }
    go(1);
  }

  async function generate() {
    setBusy(true);
    setInterview(null);
    setStep("plan");
    try {
      const iv = await api<InterviewDetail>("/interviews", {
        body: {
          role_key: role,
          interview_type: itype,
          duration_minutes: duration,
          difficulty,
          resume_id: resume?.id ?? null,
          jd_id: jdMode === "role" ? null : (jd?.id ?? null),
        },
      });
      setInterview(iv);
    } catch (e) {
      toast.error(errorMessage(e));
      setStep("preferences");
    } finally {
      setBusy(false);
    }
  }

  async function confirm() {
    if (!interview) return;
    setBusy(true);
    await api("/me/profile", { method: "PUT", body: { onboarding_completed: true } }).catch(() => undefined);
    await refresh();
    router.push(`/interviews/${interview.id}/setup`);
  }

  const roleInfo = catalog?.roles.find((r) => r.key === role);

  return (
    <div className="mx-auto max-w-3xl">
      <ol className="mb-8 flex items-center gap-2 text-xs" aria-label="Progress">
        {steps.map((s, i) => (
          <li key={s} className="flex flex-1 items-center gap-2">
            <span
              className={cn(
                "grid size-6 shrink-0 place-items-center rounded-full border text-[11px] font-semibold",
                i < idx ? "border-primary bg-primary text-primary-foreground" : i === idx ? "border-primary text-primary" : "text-muted-foreground",
              )}
              aria-current={i === idx ? "step" : undefined}
            >
              {i < idx ? <Check className="size-3.5" /> : i + 1}
            </span>
            <span className={cn("hidden sm:inline", i === idx ? "font-medium" : "text-muted-foreground")}>{STEP_LABELS[s]}</span>
            {i < steps.length - 1 && <span className="h-px flex-1 bg-border" />}
          </li>
        ))}
      </ol>

      <div key={step} className="animate-fade-up rounded-2xl border bg-card p-6 sm:p-8">
        {step === "profile" && (
          <div className="space-y-5">
            <div>
              <h2 className="text-xl font-semibold">Tell us about you</h2>
              <p className="text-sm text-muted-foreground">This calibrates question difficulty and the role-specific topics.</p>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="name">Full name</Label>
                <Input id="name" value={name} onChange={(e) => setName(e.target.value)} className="h-10" />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="email">Email</Label>
                <Input id="email" value={profile?.email ?? ""} disabled className="h-10" />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="years">Years of experience</Label>
                <Input id="years" type="number" min={0} max={50} step={0.5} value={years} onChange={(e) => setYears(e.target.value)} className="h-10" placeholder="e.g. 2" />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="role">Target role</Label>
                <NativeSelect id="role" value={role} onChange={(e) => setRole(e.target.value)} className="h-10">
                  {catalog?.roles.map((r) => (
                    <option key={r.key} value={r.key}>
                      {r.title}
                    </option>
                  ))}
                </NativeSelect>
              </div>
            </div>
            {roleInfo && <p className="text-xs text-muted-foreground">{roleInfo.description}</p>}
            <div className="flex justify-end">
              <Button onClick={saveProfile} disabled={busy || !name.trim()} className="h-10">
                {busy && <Spinner />} Continue <ArrowRight className="size-4" />
              </Button>
            </div>
          </div>
        )}

        {step === "resume" && (
          <div className="space-y-5">
            <div>
              <h2 className="text-xl font-semibold">Upload your resume</h2>
              <p className="text-sm text-muted-foreground">The interviewer will only reference skills that actually appear in it.</p>
            </div>
            {resume ? (
              <div className="flex items-center justify-between rounded-xl border bg-muted/40 p-4">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{resume.filename}</p>
                  {resume.detected_skills && <p className="mt-1 text-xs text-muted-foreground">Detected: {resume.detected_skills.slice(0, 10).join(", ") || "no known skills"}</p>}
                </div>
                <Button variant="ghost" size="icon-sm" aria-label="Remove resume" onClick={() => setResume(null)}>
                  <X className="size-4" />
                </Button>
              </div>
            ) : (
              <Dropzone accept=".pdf,.docx" onFile={uploadResume} busy={busy} label="Drop your resume here" />
            )}
            <div className="flex justify-between">
              {includeProfile ? (
                <Button variant="ghost" onClick={() => go(-1)}>
                  <ArrowLeft className="size-4" /> Back
                </Button>
              ) : (
                <span />
              )}
              <Button onClick={() => go(1)} className="h-10">
                {resume ? "Continue" : "Continue without resume"} <ArrowRight className="size-4" />
              </Button>
            </div>
          </div>
        )}

        {step === "job" && (
          <div className="space-y-5">
            <div>
              <h2 className="text-xl font-semibold">What are you preparing for?</h2>
              <p className="text-sm text-muted-foreground">A job description lets the plan prioritise the exact requirements.</p>
            </div>
            <div role="tablist" aria-label="Target job source" className="grid grid-cols-3 gap-1 rounded-lg bg-muted p-1 text-sm">
              {(["role", "paste", "upload"] as const).map((m) => (
                <button
                  key={m}
                  role="tab"
                  aria-selected={jdMode === m}
                  onClick={() => {
                    setJdMode(m);
                    setJd(null);
                  }}
                  className={cn("rounded-md py-1.5 font-medium", jdMode === m ? "bg-background shadow-sm" : "text-muted-foreground")}
                >
                  {m === "role" ? "Select role" : m === "paste" ? "Paste JD" : "Upload JD"}
                </button>
              ))}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="role2">Role</Label>
              <NativeSelect id="role2" value={role} onChange={(e) => setRole(e.target.value)} className="h-10">
                {catalog?.roles.map((r) => (
                  <option key={r.key} value={r.key}>
                    {r.title}
                  </option>
                ))}
              </NativeSelect>
            </div>
            {jdMode !== "role" && (
              <div className="space-y-1.5">
                <Label htmlFor="jdtitle">Job title (optional)</Label>
                <Input id="jdtitle" value={jdTitle} onChange={(e) => setJdTitle(e.target.value)} placeholder="e.g. Data Engineer II at Example Corp" className="h-10" />
              </div>
            )}
            {jdMode === "paste" && (
              <div className="space-y-1.5">
                <Label htmlFor="jd">Job description</Label>
                <Textarea id="jd" rows={9} value={jdText} onChange={(e) => {
                  setJdText(e.target.value);
                  setJd(null);
                }} placeholder="Paste the responsibilities and requirements…" />
              </div>
            )}
            {jdMode === "upload" &&
              (jd ? (
                <div className="rounded-xl border bg-muted/40 p-4 text-sm">
                  <p className="font-medium">{jd.title}</p>
                  <p className="mt-1 text-xs text-muted-foreground">Requirements detected: {jd.detected_skills.join(", ") || "none recognised"}</p>
                </div>
              ) : (
                <Dropzone accept=".pdf,.docx,.txt" onFile={uploadJd} busy={busy} label="Drop the job description here" />
              ))}
            <div className="flex justify-between">
              <Button variant="ghost" onClick={() => go(-1)}>
                <ArrowLeft className="size-4" /> Back
              </Button>
              <Button onClick={continueFromJob} disabled={busy || (jdMode === "upload" && !jd)} className="h-10">
                {busy && <Spinner />} Continue <ArrowRight className="size-4" />
              </Button>
            </div>
          </div>
        )}

        {step === "preferences" && (
          <div className="space-y-6">
            <div>
              <h2 className="text-xl font-semibold">Interview preferences</h2>
              <p className="text-sm text-muted-foreground">You can run as many interviews as your plan allows.</p>
            </div>
            <fieldset className="space-y-2">
              <legend className="text-sm font-medium">Duration</legend>
              <div className="grid grid-cols-3 gap-2">
                {(catalog?.durations ?? [30, 45, 60]).map((d) => (
                  <ChoiceCard key={d} selected={duration === d} onClick={() => setDuration(d)} title={`${d} minutes`} />
                ))}
              </div>
            </fieldset>
            <fieldset className="space-y-2">
              <legend className="text-sm font-medium">Difficulty</legend>
              <div className="grid grid-cols-3 gap-2">
                {["easy", "medium", "hard"].map((d) => (
                  <ChoiceCard key={d} selected={difficulty === d} onClick={() => setDifficulty(d)} title={d[0].toUpperCase() + d.slice(1)} />
                ))}
              </div>
            </fieldset>
            <fieldset className="space-y-2">
              <legend className="text-sm font-medium">Interview type</legend>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
                {(catalog?.interview_types ?? []).map((t) => (
                  <ChoiceCard key={t} selected={itype === t} onClick={() => setItype(t)} title={INTERVIEW_TYPE_LABELS[t] ?? t} />
                ))}
              </div>
            </fieldset>
            <div className="flex justify-between">
              <Button variant="ghost" onClick={() => go(-1)}>
                <ArrowLeft className="size-4" /> Back
              </Button>
              <Button onClick={generate} className="h-10">
                <Sparkles className="size-4" /> Generate my plan
              </Button>
            </div>
          </div>
        )}

        {step === "plan" && (
          <div className="space-y-6">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <h2 className="text-xl font-semibold">Your interview plan</h2>
                <p className="text-sm text-muted-foreground">{interview ? interview.title : "Analysing your resume and the role…"}</p>
              </div>
              <MockNotice show={config?.ai_is_mock} />
            </div>
            {!interview ? (
              <div className="space-y-3" aria-busy>
                {["Reading your resume", "Matching job requirements", "Choosing topics and difficulty", "Building rounds"].map((t, i) => (
                  <div key={t} className="flex items-center gap-3 text-sm text-muted-foreground" style={{ animation: `fade-up .4s ${i * 0.25}s both` }}>
                    <Spinner /> {t}
                  </div>
                ))}
              </div>
            ) : (
              <>
                <PlanView plan={interview.plan} analysis={interview.analysis} />
                <div className="flex flex-wrap justify-between gap-2">
                  <Button variant="ghost" onClick={() => setStep("preferences")}>
                    <ArrowLeft className="size-4" /> Adjust preferences
                  </Button>
                  <Button onClick={confirm} disabled={busy} className="h-10">
                    {busy && <Spinner />} Confirm plan <ArrowRight className="size-4" />
                  </Button>
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function ChoiceCard({ selected, onClick, title }: { selected: boolean; onClick: () => void; title: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      className={cn(
        "rounded-lg border px-3 py-2.5 text-sm font-medium transition-colors",
        selected ? "border-primary bg-accent text-accent-foreground ring-1 ring-primary" : "hover:bg-muted",
      )}
    >
      {title}
    </button>
  );
}
