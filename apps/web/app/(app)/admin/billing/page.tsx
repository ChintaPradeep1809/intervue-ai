"use client";

import { useState } from "react";
import { toast } from "sonner";

import { RequireRole } from "@/components/layout/app-shell";
import { ErrorState, LoadingBlock, PageHeader, Spinner } from "@/components/shared/primitives";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { api, errorMessage } from "@/lib/api";
import { useApi } from "@/lib/use-api";

interface Plan {
  id: string;
  key: string;
  name: string;
  audience: string;
  price_monthly_usd: number;
  price_monthly_inr: number;
  limits: Record<string, number | null>;
  features: string[];
  is_public: boolean;
}
interface Billing {
  plans: Plan[];
  subscriptions: Record<string, number>;
  pricing: Record<string, unknown>;
  fx_rate_usd_inr: number;
  note: string;
}

export default function BillingPage() {
  return (
    <RequireRole roles={["super_admin"]}>
      <BillingView />
    </RequireRole>
  );
}

function PlanEditor({ plan, subs, onSaved }: { plan: Plan; subs: number; onSaved: () => void }) {
  const [p, setP] = useState(plan);
  const [busy, setBusy] = useState(false);
  return (
    <div className="space-y-3 rounded-xl border bg-card p-5">
      <div className="flex items-center justify-between">
        <p className="font-medium">{p.name}</p>
        <span className="text-xs text-muted-foreground">{p.audience} · {subs} subscriptions</span>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div className="space-y-1"><Label htmlFor={`${p.key}-usd`} className="text-xs">USD / month</Label><Input id={`${p.key}-usd`} type="number" min={0} value={p.price_monthly_usd} onChange={(e) => setP({ ...p, price_monthly_usd: Number(e.target.value) })} /></div>
        <div className="space-y-1"><Label htmlFor={`${p.key}-inr`} className="text-xs">INR / month</Label><Input id={`${p.key}-inr`} type="number" min={0} value={p.price_monthly_inr} onChange={(e) => setP({ ...p, price_monthly_inr: Number(e.target.value) })} /></div>
        {Object.entries(p.limits).map(([k, v]) => (
          <div key={k} className="space-y-1">
            <Label htmlFor={`${p.key}-${k}`} className="text-xs">{k.replace(/_/g, " ")}</Label>
            <Input id={`${p.key}-${k}`} type="number" min={0} placeholder="Unlimited" value={v ?? ""} onChange={(e) => setP({ ...p, limits: { ...p.limits, [k]: e.target.value === "" ? null : Number(e.target.value) } })} />
          </div>
        ))}
      </div>
      <div className="space-y-1">
        <Label htmlFor={`${p.key}-f`} className="text-xs">Features (one per line)</Label>
        <Textarea id={`${p.key}-f`} rows={3} value={p.features.join("\n")} onChange={(e) => setP({ ...p, features: e.target.value.split("\n").filter(Boolean) })} />
      </div>
      <Button
        size="sm"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          try {
            await api(`/admin/billing/plans/${p.id}`, { method: "PUT", body: { name: p.name, price_monthly_usd: p.price_monthly_usd, price_monthly_inr: p.price_monthly_inr, limits: p.limits, features: p.features, is_public: p.is_public } });
            toast.success(`${p.name} saved`);
            onSaved();
          } catch (e) {
            toast.error(errorMessage(e));
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy && <Spinner />} Save plan
      </Button>
    </div>
  );
}

function BillingView() {
  const { data, error, loading, reload } = useApi<Billing>("/admin/billing");
  const [pricing, setPricing] = useState<string | null>(null);
  const [fx, setFx] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (loading) return <LoadingBlock rows={4} />;
  if (error || !data) return <ErrorState message={error?.message ?? "Could not load billing."} onRetry={reload} />;
  const pricingText = pricing ?? JSON.stringify(data.pricing, null, 2);
  const fxText = fx ?? String(data.fx_rate_usd_inr);
  return (
    <>
      <PageHeader title="Plans & pricing" description={data.note} />
      <div className="grid gap-4 md:grid-cols-2">
        {data.plans.map((p) => <PlanEditor key={p.id} plan={p} subs={data.subscriptions[p.key] ?? 0} onSaved={reload} />)}
      </div>
      <section className="mt-8 space-y-3 rounded-xl border bg-card p-5">
        <h2 className="font-medium">Provider pricing (cost model)</h2>
        <p className="text-sm text-muted-foreground">Unit prices used to estimate cost per interview. Keys are <code>provider:model</code>; verify against provider pricing pages.</p>
        <Textarea aria-label="Pricing JSON" rows={16} className="font-mono text-xs" value={pricingText} onChange={(e) => setPricing(e.target.value)} />
        <div className="flex items-end gap-3">
          <div className="space-y-1">
            <Label htmlFor="fx">USD → INR rate</Label>
            <Input id="fx" type="number" step="0.01" min={1} value={fxText} onChange={(e) => setFx(e.target.value)} className="w-32" />
          </div>
          <Button
            disabled={busy}
            onClick={async () => {
              let parsed: unknown;
              try {
                parsed = JSON.parse(pricingText);
              } catch {
                toast.error("Pricing must be valid JSON.");
                return;
              }
              setBusy(true);
              try {
                await api("/admin/billing/pricing", { method: "PUT", body: { pricing: parsed as Record<string, unknown>, usd_inr: Number(fxText) } });
                toast.success("Pricing updated");
                setPricing(null);
                setFx(null);
                reload();
              } catch (e) {
                toast.error(errorMessage(e));
              } finally {
                setBusy(false);
              }
            }}
          >
            {busy && <Spinner />} Save pricing
          </Button>
        </div>
      </section>
    </>
  );
}
