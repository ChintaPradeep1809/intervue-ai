"use client";

import { Activity, AlertTriangle, Bot, Coins, Database, HardDrive, Mic, Radio, Server, Timer } from "lucide-react";

import { RequireRole } from "@/components/layout/app-shell";
import { ErrorState, LoadingBlock, PageHeader, StatCard } from "@/components/shared/primitives";
import { Button } from "@/components/ui/button";
import { formatDateTime } from "@/lib/format";
import { useApi } from "@/lib/use-api";
import { cn } from "@/lib/utils";

interface CommandCenter {
  providers: {
    ai: { provider: string; model: string; is_mock: boolean; fallback_model: string | null };
    voice: { provider: string; stt: string; tts: string };
    embeddings: { provider: string; model: string };
    screen_analysis: string;
    storage: string;
  };
  database: string;
  storage: string;
  worker: { status: string; backend?: string; error?: string };
  usage_30d: Record<string, { input_tokens: number; output_tokens: number; quantity: number; cost_usd: number; events: number }>;
  ai_tokens_30d: number;
  voice_minutes_30d: number;
  estimated_cost_usd_30d: number;
  estimated_cost_inr_30d: number;
  avg_cost_per_interview_usd: number | null;
  active_interviews: { connected: number; in_progress: number };
  interviews_by_status: Record<string, number>;
  metrics: {
    uptime_seconds: number;
    counters: Record<string, number>;
    latency_ms: Record<string, { count: number; p50: number; p95: number }>;
    recent_errors: { at: number; where: string; message: string; request_id: string | null }[];
  };
  fx_rate_usd_inr: number;
}

function Health({ label, status, detail, icon: Icon }: { label: string; status: string; detail?: string; icon: React.ComponentType<{ className?: string }> }) {
  const ok = status === "ok";
  return (
    <div className="flex items-center gap-3 rounded-xl border bg-card p-4">
      <Icon className="size-5 text-muted-foreground" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">{label}</p>
        {detail && <p className="truncate text-xs text-muted-foreground">{detail}</p>}
      </div>
      <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", ok ? "bg-success/15 text-success" : "bg-destructive/10 text-destructive")}>{ok ? "Healthy" : "Down"}</span>
    </div>
  );
}

export default function CommandCenterPage() {
  return (
    <RequireRole roles={["super_admin"]}>
      <CommandCenterView />
    </RequireRole>
  );
}

function CommandCenterView() {
  const { data, error, loading, reload } = useApi<CommandCenter>("/admin/command-center");
  if (loading) return <LoadingBlock rows={4} />;
  if (error || !data) return <ErrorState message={error?.message ?? "Could not load."} onRetry={reload} />;
  const p = data.providers;
  const lat = data.metrics.latency_ms;
  const latencyRows = Object.entries(lat).sort((a, b) => b[1].count - a[1].count);
  return (
    <>
      <PageHeader
        eyebrow="Platform"
        title="Command center"
        description="Providers, health, usage and unit economics — the numbers that matter before commercial launch."
        actions={<Button variant="outline" className="h-9" onClick={reload}>Refresh</Button>}
      />
      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
        <Health label="AI provider" status="ok" icon={Bot} detail={`${p.ai.provider} · ${p.ai.model}${p.ai.is_mock ? " (deterministic local engine)" : ""}${p.ai.fallback_model ? ` · fallback ${p.ai.fallback_model}` : ""}`} />
        <Health label="Voice provider" status="ok" icon={Mic} detail={`${p.voice.provider} · STT ${p.voice.stt} · TTS ${p.voice.tts}`} />
        <Health label="Database" status={data.database} icon={Database} detail="PostgreSQL" />
        <Health label="Storage" status={data.storage} icon={HardDrive} detail={p.storage} />
        <Health label="Code execution worker" status={data.worker.status} icon={Server} detail={data.worker.backend ? `backend: ${data.worker.backend}` : data.worker.error} />
        <Health label="Embeddings / RAG" status="ok" icon={Radio} detail={`${p.embeddings.provider} · ${p.embeddings.model}`} />
      </div>

      <div className="mt-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="AI tokens (30d)" value={data.ai_tokens_30d.toLocaleString()} icon={Bot} />
        <StatCard label="Voice minutes (30d)" value={data.voice_minutes_30d} icon={Mic} />
        <StatCard label="Estimated cost (30d)" value={`$${data.estimated_cost_usd_30d.toFixed(2)}`} hint={`₹${data.estimated_cost_inr_30d.toFixed(2)} @ ${data.fx_rate_usd_inr}`} icon={Coins} />
        <StatCard label="Avg cost / interview" value={data.avg_cost_per_interview_usd !== null ? `$${data.avg_cost_per_interview_usd.toFixed(4)}` : "—"} icon={Coins} />
        <StatCard label="Active interviews" value={data.active_interviews.in_progress} hint={`${data.active_interviews.connected} connected now`} icon={Activity} />
        <StatCard label="Completed" value={data.interviews_by_status.completed ?? 0} hint={`${data.metrics.counters.interviews_failed ?? 0} failed reports`} icon={Timer} />
        <StatCard label="AI fallbacks" value={data.metrics.counters.ai_fallbacks ?? 0} hint={`${data.metrics.counters.ai_calls ?? 0} AI calls since start`} icon={AlertTriangle} />
        <StatCard label="Errors" value={data.metrics.counters.errors ?? 0} hint={`Uptime ${Math.round(data.metrics.uptime_seconds / 60)} min`} icon={AlertTriangle} />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <section className="rounded-xl border bg-card">
          <h2 className="border-b px-4 py-3 text-sm font-medium">Latency (since process start)</h2>
          {latencyRows.length ? (
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-muted-foreground">
                <tr><th className="px-4 py-2 font-medium">Operation</th><th className="px-4 py-2 font-medium">Count</th><th className="px-4 py-2 font-medium">p50</th><th className="px-4 py-2 font-medium">p95</th></tr>
              </thead>
              <tbody>
                {latencyRows.map(([k, v]) => (
                  <tr key={k} className="border-t">
                    <td className="px-4 py-2 font-mono text-xs">{k}</td>
                    <td className="px-4 py-2 tabular">{v.count}</td>
                    <td className="px-4 py-2 tabular">{v.p50} ms</td>
                    <td className="px-4 py-2 tabular">{v.p95} ms</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="p-4 text-sm text-muted-foreground">No requests recorded yet.</p>
          )}
        </section>
        <section className="rounded-xl border bg-card">
          <h2 className="border-b px-4 py-3 text-sm font-medium">Usage by kind (30 days)</h2>
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-muted-foreground">
              <tr><th className="px-4 py-2 font-medium">Kind</th><th className="px-4 py-2 font-medium">Events</th><th className="px-4 py-2 font-medium">Tokens / qty</th><th className="px-4 py-2 font-medium">Cost</th></tr>
            </thead>
            <tbody>
              {Object.entries(data.usage_30d).map(([k, v]) => (
                <tr key={k} className="border-t">
                  <td className="px-4 py-2">{k}</td>
                  <td className="px-4 py-2 tabular">{v.events}</td>
                  <td className="px-4 py-2 tabular">{k === "llm" ? (v.input_tokens + v.output_tokens).toLocaleString() : Math.round(v.quantity).toLocaleString()}</td>
                  <td className="px-4 py-2 tabular">${v.cost_usd.toFixed(4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
        <section className="rounded-xl border bg-card lg:col-span-2">
          <h2 className="border-b px-4 py-3 text-sm font-medium">Recent errors</h2>
          {data.metrics.recent_errors.length ? (
            <ul className="divide-y text-sm">
              {data.metrics.recent_errors.map((e, i) => (
                <li key={i} className="px-4 py-2">
                  <span className="font-mono text-xs text-muted-foreground">{formatDateTime(new Date(e.at * 1000))} · {e.where}{e.request_id ? ` · ${e.request_id}` : ""}</span>
                  <p>{e.message}</p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="p-4 text-sm text-muted-foreground">No errors since the API started.</p>
          )}
        </section>
      </div>
    </>
  );
}
