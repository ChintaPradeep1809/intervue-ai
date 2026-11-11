"use client";

import { TrendArea } from "@/components/dashboard/charts";
import { RequireRole } from "@/components/layout/app-shell";
import { ErrorState, LoadingBlock, PageHeader, StatCard } from "@/components/shared/primitives";
import { formatDate, formatDateTime } from "@/lib/format";
import { useApi } from "@/lib/use-api";

interface Usage {
  daily: { date: string; cost_usd: number; llm_tokens: number; voice_seconds: number }[];
  by_task: { task: string; calls: number; tokens: number; cost_usd: number; avg_latency_ms: number; fallbacks: number }[];
  interview_costs: {
    interview_id: string;
    title: string;
    duration_seconds: number;
    llm_input_tokens: number;
    llm_output_tokens: number;
    voice_seconds: number;
    code_execution_seconds: number;
    storage_bytes: number;
    estimated_cost_usd: number;
    estimated_cost_inr: number;
    updated_at: string;
  }[];
  avg_cost_per_interview_usd: number;
  unit_economics: { plan: string; price_usd: number; interviews: number; est_cost_at_limit_usd: number; gross_margin_pct: number }[];
  fx_rate_usd_inr: number;
}

export default function UsagePage() {
  return (
    <RequireRole roles={["super_admin"]}>
      <UsageView />
    </RequireRole>
  );
}

function UsageView() {
  const { data, error, loading, reload } = useApi<Usage>("/admin/usage?days=30");
  if (loading) return <LoadingBlock rows={4} />;
  if (error || !data) return <ErrorState message={error?.message ?? "Could not load usage."} onRetry={reload} />;
  const tokens = data.daily.reduce((a, d) => a + d.llm_tokens, 0);
  const cost = data.daily.reduce((a, d) => a + d.cost_usd, 0);
  return (
    <>
      <PageHeader title="Usage & cost" description="Metered from every AI, voice, embedding, execution and storage call. Prices come from the pricing configuration." />
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="LLM tokens (30d)" value={tokens.toLocaleString()} />
        <StatCard label="Estimated cost (30d)" value={`$${cost.toFixed(4)}`} hint={`₹${(cost * data.fx_rate_usd_inr).toFixed(2)}`} />
        <StatCard label="Avg cost / interview" value={`$${data.avg_cost_per_interview_usd.toFixed(4)}`} hint={`₹${(data.avg_cost_per_interview_usd * data.fx_rate_usd_inr).toFixed(3)}`} />
        <StatCard label="USD → INR" value={data.fx_rate_usd_inr} hint="Configurable in Plans & pricing" />
      </div>
      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <section className="rounded-xl border bg-card p-5">
          <h2 className="mb-2 text-sm font-medium">LLM tokens per day</h2>
          <TrendArea data={data.daily.map((d) => ({ ...d, label: formatDate(d.date, { month: "short", day: "numeric" }) }))} xKey="label" yKey="llm_tokens" />
        </section>
        <section className="rounded-xl border bg-card p-5">
          <h2 className="mb-3 text-sm font-medium">Unit economics at plan limits</h2>
          {data.unit_economics.length ? (
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-muted-foreground"><tr><th className="py-1.5 font-medium">Plan</th><th className="py-1.5 font-medium">Price</th><th className="py-1.5 font-medium">Interviews</th><th className="py-1.5 font-medium">Est. cost</th><th className="py-1.5 font-medium">Gross margin</th></tr></thead>
              <tbody>
                {data.unit_economics.map((u) => (
                  <tr key={u.plan} className="border-t">
                    <td className="py-1.5">{u.plan}</td>
                    <td className="py-1.5 tabular">${u.price_usd}</td>
                    <td className="py-1.5 tabular">{u.interviews}</td>
                    <td className="py-1.5 tabular">${u.est_cost_at_limit_usd}</td>
                    <td className="py-1.5 tabular">{u.gross_margin_pct}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="text-sm text-muted-foreground">Set plan prices and limits to see margins.</p>
          )}
          <p className="mt-2 text-xs text-muted-foreground">Uses the average measured cost per completed interview. With the mock AI provider costs are $0.</p>
        </section>
        <section className="rounded-xl border bg-card lg:col-span-2">
          <h2 className="border-b px-4 py-3 text-sm font-medium">AI usage by task</h2>
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-muted-foreground"><tr>{["Task", "Calls", "Tokens", "Cost", "Avg latency", "Fallbacks"].map((h) => <th key={h} className="px-4 py-2 font-medium">{h}</th>)}</tr></thead>
            <tbody>
              {data.by_task.map((t) => (
                <tr key={t.task} className="border-t">
                  <td className="px-4 py-2 font-mono text-xs">{t.task}</td>
                  <td className="px-4 py-2 tabular">{t.calls}</td>
                  <td className="px-4 py-2 tabular">{t.tokens.toLocaleString()}</td>
                  <td className="px-4 py-2 tabular">${t.cost_usd.toFixed(4)}</td>
                  <td className="px-4 py-2 tabular">{t.avg_latency_ms} ms</td>
                  <td className="px-4 py-2 tabular">{t.fallbacks}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
        <section className="overflow-x-auto rounded-xl border bg-card lg:col-span-2">
          <h2 className="border-b px-4 py-3 text-sm font-medium">Cost per interview</h2>
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-muted-foreground"><tr>{["Interview", "Duration", "LLM in/out", "Voice", "Execution", "Storage", "USD", "INR", "Updated"].map((h) => <th key={h} className="px-4 py-2 font-medium whitespace-nowrap">{h}</th>)}</tr></thead>
            <tbody>
              {data.interview_costs.map((c) => (
                <tr key={c.interview_id} className="border-t">
                  <td className="max-w-64 truncate px-4 py-2" title={c.title}>{c.title}</td>
                  <td className="px-4 py-2 tabular">{Math.round(c.duration_seconds / 60)} min</td>
                  <td className="px-4 py-2 tabular whitespace-nowrap">{c.llm_input_tokens.toLocaleString()} / {c.llm_output_tokens.toLocaleString()}</td>
                  <td className="px-4 py-2 tabular">{Math.round(c.voice_seconds)} s</td>
                  <td className="px-4 py-2 tabular">{c.code_execution_seconds.toFixed(1)} s</td>
                  <td className="px-4 py-2 tabular">{(c.storage_bytes / 1024).toFixed(0)} KB</td>
                  <td className="px-4 py-2 tabular">${c.estimated_cost_usd.toFixed(4)}</td>
                  <td className="px-4 py-2 tabular">₹{c.estimated_cost_inr.toFixed(3)}</td>
                  <td className="px-4 py-2 whitespace-nowrap text-muted-foreground">{formatDateTime(c.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>
    </>
  );
}
