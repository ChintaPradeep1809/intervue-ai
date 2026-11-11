"use client";

import { useState } from "react";
import { toast } from "sonner";

import { RequireRole } from "@/components/layout/app-shell";
import { EmptyState, ErrorState, LoadingBlock, NativeSelect, PageHeader } from "@/components/shared/primitives";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, errorMessage } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useApi } from "@/lib/use-api";

type Limits = { interviews_per_month: number | null; voice_minutes_per_month: number | null; ai_tokens_per_month: number | null; seats: number | null };
interface AdminOrg {
  id: string;
  name: string;
  kind: string;
  created_at: string;
  interviews: number;
  members: number;
  cost_usd: number;
  plan: string | null;
  subscription_status: string | null;
  limits: Limits | null;
}

export default function AdminOrgsPage() {
  return (
    <RequireRole roles={["super_admin"]}>
      <Orgs />
    </RequireRole>
  );
}

function Orgs() {
  const { data, error, loading, reload } = useApi<{ items: AdminOrg[] }>("/admin/organizations");
  const { data: billing } = useApi<{ plans: { key: string; name: string }[] }>("/admin/billing");
  const [edit, setEdit] = useState<AdminOrg | null>(null);
  const [form, setForm] = useState<{ plan_key: string } & Record<keyof Limits, string>>({ plan_key: "", interviews_per_month: "", voice_minutes_per_month: "", ai_tokens_per_month: "", seats: "" });

  function open(o: AdminOrg) {
    setEdit(o);
    setForm({
      plan_key: o.plan ?? "",
      interviews_per_month: o.limits?.interviews_per_month?.toString() ?? "",
      voice_minutes_per_month: o.limits?.voice_minutes_per_month?.toString() ?? "",
      ai_tokens_per_month: o.limits?.ai_tokens_per_month?.toString() ?? "",
      seats: o.limits?.seats?.toString() ?? "",
    });
  }

  return (
    <>
      <PageHeader title="Organizations" description="Plans, limits, usage and cost per organization." />
      {loading ? (
        <LoadingBlock rows={4} />
      ) : error ? (
        <ErrorState message={error.message} onRetry={reload} />
      ) : !data?.items.length ? (
        <EmptyState title="No organizations yet" />
      ) : (
        <div className="overflow-x-auto rounded-xl border bg-card">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-muted-foreground">
              <tr className="border-b">
                {["Organization", "Plan", "Members", "Interviews", "AI cost", "Limits", "Created", ""].map((h) => <th key={h} className="px-4 py-2.5 font-medium">{h}</th>)}
              </tr>
            </thead>
            <tbody>
              {data.items.map((o) => (
                <tr key={o.id} className="border-b last:border-0">
                  <td className="px-4 py-2.5"><p className="font-medium">{o.name}</p><p className="text-xs text-muted-foreground capitalize">{o.kind}</p></td>
                  <td className="px-4 py-2.5">{o.plan ?? "—"} {o.subscription_status && <span className="text-xs text-muted-foreground">({o.subscription_status})</span>}</td>
                  <td className="px-4 py-2.5 tabular">{o.members}</td>
                  <td className="px-4 py-2.5 tabular">{o.interviews}</td>
                  <td className="px-4 py-2.5 tabular">${o.cost_usd.toFixed(4)}</td>
                  <td className="px-4 py-2.5 text-xs text-muted-foreground">{o.limits?.interviews_per_month != null ? `${o.limits.interviews_per_month} interviews/mo` : "Plan default"}</td>
                  <td className="px-4 py-2.5 text-muted-foreground">{formatDate(o.created_at)}</td>
                  <td className="px-4 py-2.5"><Button variant="outline" size="sm" onClick={() => open(o)}>Manage</Button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <Dialog open={!!edit} onOpenChange={(o) => !o && setEdit(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Manage {edit?.name}</DialogTitle></DialogHeader>
          <div className="grid gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="pl">Plan</Label>
              <NativeSelect id="pl" value={form.plan_key} onChange={(e) => setForm({ ...form, plan_key: e.target.value })}>
                <option value="">No change</option>
                {billing?.plans.map((p) => <option key={p.key} value={p.key}>{p.name}</option>)}
              </NativeSelect>
            </div>
            <p className="text-xs text-muted-foreground">Limit overrides (leave blank to use the plan default):</p>
            <div className="grid grid-cols-2 gap-3">
              {([["interviews_per_month", "Interviews / month"], ["voice_minutes_per_month", "Voice minutes / month"], ["ai_tokens_per_month", "AI tokens / month"], ["seats", "Admin seats"]] as const).map(([k, label]) => (
                <div key={k} className="space-y-1.5">
                  <Label htmlFor={k}>{label}</Label>
                  <Input id={k} type="number" min={0} value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })} />
                </div>
              ))}
            </div>
          </div>
          <DialogFooter>
            <Button
              onClick={async () => {
                if (!edit) return;
                const body: Record<string, unknown> = {};
                if (form.plan_key) body.plan_key = form.plan_key;
                for (const k of ["interviews_per_month", "voice_minutes_per_month", "ai_tokens_per_month", "seats"] as const) body[k] = form[k] === "" ? null : Number(form[k]);
                try {
                  await api(`/admin/organizations/${edit.id}`, { method: "PATCH", body });
                  toast.success("Organization updated");
                  setEdit(null);
                  reload();
                } catch (e) {
                  toast.error(errorMessage(e));
                }
              }}
            >
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
