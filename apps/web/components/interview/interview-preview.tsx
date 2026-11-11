import { Code2, Mic, MonitorUp, PhoneOff, Wifi } from "lucide-react";

import { Waveform } from "./waveform";

/** Static product preview for the landing page (illustrative, not live data). */
export function InterviewPreview() {
  return (
    <div className="relative" aria-label="Preview of the interview room">
      <div className="overflow-hidden rounded-2xl border bg-studio text-studio-foreground shadow-2xl shadow-primary/10">
        <div className="flex items-center justify-between border-b border-white/10 px-4 py-3 text-xs">
          <div className="flex items-center gap-2">
            <span className="size-2 rounded-full bg-success" />
            <span className="font-medium">AI Interviewer</span>
            <span className="text-white/50">· AWS Data Engineer</span>
          </div>
          <div className="flex items-center gap-3 text-white/60">
            <span className="tabular">27:41</span>
            <span className="inline-flex items-center gap-1"><Wifi className="size-3.5" /> Connected</span>
          </div>
        </div>
        <div className="space-y-5 px-6 py-7">
          <div className="flex items-center gap-4">
            <div className="grid size-12 place-items-center rounded-full bg-primary/25 ring-1 ring-primary/40">
              <span className="text-sm font-semibold">AI</span>
            </div>
            <Waveform active bars={28} className="h-10 flex-1 text-primary" />
            <span className="rounded-full bg-white/10 px-2 py-0.5 text-[11px]">Speaking</span>
          </div>
          <div className="rounded-xl bg-white/5 p-4 ring-1 ring-white/10">
            <p className="text-[11px] tracking-wide text-white/50 uppercase">Follow-up · PySpark</p>
            <p className="mt-1.5 text-[15px] leading-relaxed">
              That&apos;s true. What happens if the data contains significant key skew?
            </p>
          </div>
          <div className="space-y-2 text-sm">
            <p className="text-white/50">
              <span className="text-white/70">You:</span> I would use Spark because it&apos;s distributed and we can partition by customer…
            </p>
            <p className="text-white/40 italic">Listening…</p>
          </div>
        </div>
        <div className="flex items-center justify-center gap-2 border-t border-white/10 px-4 py-3">
          {[Mic, MonitorUp, Code2].map((Icon, i) => (
            <span key={i} className="grid size-9 place-items-center rounded-full bg-white/10">
              <Icon className="size-4" />
            </span>
          ))}
          <span className="ml-2 inline-flex h-9 items-center gap-1.5 rounded-full bg-destructive/90 px-3 text-xs font-medium">
            <PhoneOff className="size-3.5" /> End
          </span>
        </div>
      </div>
      <div className="absolute -right-4 -bottom-16 hidden w-56 rounded-xl border bg-card p-4 text-card-foreground shadow-lg sm:block">
        <p className="text-xs text-muted-foreground">SQL · Evidence</p>
        <p className="mt-1 text-sm">“…ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY updated_at DESC)…”</p>
        <div className="mt-3 flex items-center justify-between text-xs">
          <span className="text-muted-foreground">Window functions</span>
          <span className="font-semibold text-success">84</span>
        </div>
      </div>
    </div>
  );
}
