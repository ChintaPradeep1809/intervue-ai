"use client";

import { ROUND_KIND_LABELS } from "@intervue/config";
import type { Catalog } from "@intervue/types";
import { Copy, FileStack, Link2, Pencil, Plus, Trash2, X } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { OrgGate } from "@/components/admin/org-gate";
import { EmptyState, ErrorState, LoadingBlock, NativeSelect, PageHeader, Spinner } from "@/components/shared/primitives";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { api, errorMessage } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useApi } from "@/lib/use-api";
import { cn } from "@/lib/utils";

interface RoundForm {
  kind: string;
  title: string;
  minutes: number;
  topics: string[];
  question_count?: number | null;
  language?: string | null;
}
interface Invite {
  id: string;
  token: string;
  label: string;
  url: string;
  uses: number;
  max_uses: number;
  expires_at: string | null;
  is_active: boolean;
  email_domain: string | null;
}
interface Template {
  id: string;
  name: string;
  role_key: string;
  role_title: string;
  experience_level: string;
  duration_minutes: number;
  difficulty: string;
  interview_type: string;
  rounds: RoundForm[];
  scoring_weights: Record<string, number>;
  jd_text: string;
  is_active: boolean;
  is_global: boolean;
  invites: Invite[];
}
type TemplateForm = Omit<Template, "id" | "role_title" | "duration_minutes" | "is_global" | "invites"> & { id?: string };

const EMPTY: TemplateForm = {
  name: "",
  role_key: "aws_data_engineer",
  experience_level: "junior",
  difficulty: "medium",
  interview_type: "full",
  rounds: [
    { kind: "introduction", title: "Introduction", minutes: 5, topics: ["introduction"] },
    { kind: "technical", title: "Technical", minutes: 15, topics: ["sql", "python"], question_count: 3 },
    { kind: "behavioral", title: "Behavioral", minutes: 5, topics: ["behavioral"] },
  ],
  scoring_weights: {},
  jd_text: "",
  is_active: true,
};

export default function OrgInterviewsPage() {
  return (
    <OrgGate>
      <Templates />
    </OrgGate>
  );
}

function Templates() {
  const { data, error, loading, reload } = useApi<{ items: Template[] }>("/organization/templates");
  const { data: catalog } = useApi<Catalog>("/catalog");
  const [editing, setEditing] = useState<TemplateForm | null>(null);
  const [inviteFor, setInviteFor] = useState<Template | null>(null);

  const own = data?.items.filter((t) => !t.is_global) ?? [];
  const library = data?.items.filter((t) => t.is_global) ?? [];

  async function remove(t: Template) {
    if (!confirm(`Delete template "${t.name}"? Existing interviews are kept.`)) return;
    try {
      await api(`/organization/templates/${t.id}`, { method: "DELETE" });
      reload();
    } catch (e) {
      toast.error(errorMessage(e));
    }
  }

  return (
    <>
      <PageHeader
        title="Templates & invite links"
        description="Define interview stages once, then share a link with any number of candidates."
        actions={
          <Button className="h-9" onClick={() => setEditing({ ...EMPTY, rounds: EMPTY.rounds.map((r) => ({ ...r })) })}>
            <Plus className="size-4" /> New template
          </Button>
        }
      />
      {editing && catalog && <TemplateBuilder value={editing} catalog={catalog} onCancel={() => setEditing(null)} onSaved={() => { setEditing(null); reload(); }} />}
      {loading ? (
        <LoadingBlock rows={3} />
      ) : error ? (
        <ErrorState message={error.message} onRetry={reload} />
      ) : (
        <div className="space-y-8">
          <section>
            <h2 className="mb-3 text-sm font-medium">Your templates</h2>
            {own.length === 0 ? (
              <EmptyState icon={FileStack} title="No templates yet" description="Create one from scratch or duplicate a library template below." />
            ) : (
              <div className="grid gap-4 lg:grid-cols-2">
                {own.map((t) => (
                  <TemplateCard key={t.id} t={t} onEdit={() => setEditing({ ...t })} onDelete={() => remove(t)} onInvite={() => setInviteFor(t)} onToggle={reload} />
                ))}
              </div>
            )}
          </section>
          <section>
            <h2 className="mb-3 text-sm font-medium">Template library</h2>
            <div className="grid gap-4 lg:grid-cols-2">
              {library.map((t) => (
                <TemplateCard
                  key={t.id}
                  t={t}
                  library
                  onEdit={() => setEditing({ ...t, id: undefined, name: `${t.name} (copy)` })}
                  onInvite={() => setInviteFor(t)}
                  onToggle={reload}
                />
              ))}
            </div>
          </section>
        </div>
      )}
      <InviteDialog template={inviteFor} onClose={() => setInviteFor(null)} onCreated={reload} />
    </>
  );
}

function TemplateCard({
  t,
  library,
  onEdit,
  onDelete,
  onInvite,
  onToggle,
}: {
  t: Template;
  library?: boolean;
  onEdit: () => void;
  onDelete?: () => void;
  onInvite: () => void;
  onToggle: () => void;
}) {
  return (
    <div className="flex flex-col rounded-xl border bg-card p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate font-medium">{t.name}</p>
          <p className="text-xs text-muted-foreground">
            {t.role_title} · {t.experience_level} · {t.difficulty} · {t.duration_minutes} min
          </p>
        </div>
        <div className="flex shrink-0 gap-1">
          <Button variant="ghost" size="icon-sm" aria-label={library ? "Duplicate template" : "Edit template"} onClick={onEdit}>
            {library ? <Copy className="size-4" /> : <Pencil className="size-4" />}
          </Button>
          {onDelete && (
            <Button variant="ghost" size="icon-sm" aria-label="Delete template" onClick={onDelete}>
              <Trash2 className="size-4" />
            </Button>
          )}
        </div>
      </div>
      <ol className="mt-3 flex flex-wrap gap-1.5">
        {t.rounds.map((r, i) => (
          <li key={i} className="rounded-md bg-muted px-2 py-0.5 text-xs">
            {r.title || ROUND_KIND_LABELS[r.kind]} · {r.minutes}m
          </li>
        ))}
      </ol>
      {t.invites.length > 0 && (
        <ul className="mt-4 space-y-2 border-t pt-3">
          {t.invites.map((inv) => (
            <li key={inv.id} className="flex items-center gap-2 text-xs">
              <Link2 className="size-3.5 shrink-0 text-muted-foreground" />
              <span className={cn("min-w-0 flex-1 truncate", !inv.is_active && "text-muted-foreground line-through")}>{inv.label}</span>
              <span className="text-muted-foreground tabular">
                {inv.uses}/{inv.max_uses}
              </span>
              <span className="hidden text-muted-foreground sm:inline">exp {formatDate(inv.expires_at)}</span>
              <Button
                variant="ghost"
                size="icon-xs"
                aria-label="Copy invite link"
                onClick={() => {
                  void navigator.clipboard.writeText(inv.url);
                  toast.success("Invite link copied");
                }}
              >
                <Copy className="size-3" />
              </Button>
              <Switch
                aria-label={inv.is_active ? "Disable link" : "Enable link"}
                checked={inv.is_active}
                onCheckedChange={async (v) => {
                  await api(`/organization/invites/${inv.id}?active=${v}`, { method: "PATCH" }).catch((e) => toast.error(errorMessage(e)));
                  onToggle();
                }}
                size="sm"
              />
            </li>
          ))}
        </ul>
      )}
      <div className="mt-4 flex-1" />
      <Button variant="outline" size="sm" className="self-start" onClick={onInvite}>
        <Link2 className="size-3.5" /> Generate invite link
      </Button>
    </div>
  );
}

function InviteDialog({ template, onClose, onCreated }: { template: Template | null; onClose: () => void; onCreated: () => void }) {
  const [label, setLabel] = useState("");
  const [maxUses, setMaxUses] = useState(100);
  const [days, setDays] = useState(30);
  const [domain, setDomain] = useState("");
  const [created, setCreated] = useState<Invite | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <Dialog
      open={!!template}
      onOpenChange={(o) => {
        if (!o) {
          setCreated(null);
          onClose();
        }
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Invite link for “{template?.name}”</DialogTitle>
          <DialogDescription>Anyone with this link can sign in and take the interview. Results appear in your candidates list.</DialogDescription>
        </DialogHeader>
        {created ? (
          <div className="space-y-3">
            <div className="flex gap-2">
              <Input readOnly value={created.url} aria-label="Invite URL" onFocus={(e) => e.target.select()} />
              <Button
                onClick={() => {
                  void navigator.clipboard.writeText(created.url);
                  toast.success("Copied");
                }}
              >
                <Copy className="size-4" /> Copy
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">Share it by email, LMS or WhatsApp. You can disable it at any time.</p>
          </div>
        ) : (
          <div className="grid gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="il">Label</Label>
              <Input id="il" value={label} onChange={(e) => setLabel(e.target.value)} placeholder="e.g. Campus drive — CSE batch 2026" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="mu">Max candidates</Label>
                <Input id="mu" type="number" min={1} max={10000} value={maxUses} onChange={(e) => setMaxUses(Number(e.target.value))} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="ed">Expires in (days)</Label>
                <Input id="ed" type="number" min={1} max={365} value={days} onChange={(e) => setDays(Number(e.target.value))} />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="dm">Restrict to email domain (optional)</Label>
              <Input id="dm" value={domain} onChange={(e) => setDomain(e.target.value)} placeholder="e.g. student.example.edu" />
            </div>
          </div>
        )}
        <DialogFooter>
          {!created && (
            <Button
              disabled={busy}
              onClick={async () => {
                if (!template) return;
                setBusy(true);
                try {
                  const inv = await api<Invite>(`/organization/templates/${template.id}/invites`, {
                    body: { label, max_uses: maxUses, expires_in_days: days, email_domain: domain || null },
                  });
                  setCreated(inv);
                  onCreated();
                } catch (e) {
                  toast.error(errorMessage(e));
                } finally {
                  setBusy(false);
                }
              }}
            >
              {busy && <Spinner />} Create link
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function TemplateBuilder({ value, catalog, onCancel, onSaved }: { value: TemplateForm; catalog: Catalog; onCancel: () => void; onSaved: () => void }) {
  const [t, setT] = useState<TemplateForm>(value);
  const [busy, setBusy] = useState(false);
  const total = t.rounds.reduce((a, r) => a + (Number(r.minutes) || 0), 0);
  const topics = catalog.topics.filter((x) => !["introduction", "behavioral", "system_design"].includes(x.key));
  const setRound = (i: number, patch: Partial<RoundForm>) => setT({ ...t, rounds: t.rounds.map((r, j) => (j === i ? { ...r, ...patch } : r)) });
  const weightTopics = Array.from(new Set(t.rounds.flatMap((r) => r.topics)));

  async function save() {
    setBusy(true);
    try {
      const body = { ...t, rounds: t.rounds.map((r) => ({ ...r, minutes: Number(r.minutes), question_count: r.question_count ? Number(r.question_count) : null })) };
      if (t.id) await api(`/organization/templates/${t.id}`, { method: "PUT", body });
      else await api("/organization/templates", { body });
      toast.success("Template saved");
      onSaved();
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="mb-8 animate-fade-up rounded-2xl border bg-card p-6" aria-label="Template builder">
      <div className="mb-5 flex items-center justify-between">
        <h2 className="font-semibold">{t.id ? "Edit template" : "New template"}</h2>
        <Button variant="ghost" size="icon-sm" aria-label="Close builder" onClick={onCancel}>
          <X className="size-4" />
        </Button>
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        <div className="space-y-1.5 md:col-span-3">
          <Label htmlFor="tn">Interview name</Label>
          <Input id="tn" value={t.name} onChange={(e) => setT({ ...t, name: e.target.value })} placeholder="AWS Data Engineer — 2 Years" />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="tr">Role</Label>
          <NativeSelect id="tr" value={t.role_key} onChange={(e) => setT({ ...t, role_key: e.target.value })}>
            {catalog.roles.map((r) => <option key={r.key} value={r.key}>{r.title}</option>)}
          </NativeSelect>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="te">Experience</Label>
          <NativeSelect id="te" value={t.experience_level} onChange={(e) => setT({ ...t, experience_level: e.target.value })}>
            {["entry", "junior", "mid", "senior", "lead"].map((x) => <option key={x} value={x}>{x[0].toUpperCase() + x.slice(1)}</option>)}
          </NativeSelect>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="td">Difficulty</Label>
          <NativeSelect id="td" value={t.difficulty} onChange={(e) => setT({ ...t, difficulty: e.target.value })}>
            {["easy", "medium", "hard"].map((x) => <option key={x} value={x}>{x[0].toUpperCase() + x.slice(1)}</option>)}
          </NativeSelect>
        </div>
      </div>

      <div className="mt-6">
        <div className="mb-2 flex items-center justify-between">
          <p className="text-sm font-medium">Rounds</p>
          <span className="text-xs text-muted-foreground tabular">Total {total} min</span>
        </div>
        <ol className="space-y-2">
          {t.rounds.map((r, i) => (
            <li key={i} className="grid gap-2 rounded-lg border p-3 md:grid-cols-[150px_1fr_80px_90px_auto]">
              <NativeSelect aria-label="Round type" value={r.kind} onChange={(e) => setRound(i, { kind: e.target.value, topics: e.target.value === "technical" ? r.topics.filter((x) => topics.some((tp) => tp.key === x)) : [e.target.value === "sql" ? "sql" : e.target.value === "coding" ? "python" : e.target.value], language: e.target.value === "sql" ? "sql" : e.target.value === "coding" ? "python" : null })}>
                {catalog.round_kinds.map((k) => <option key={k} value={k}>{ROUND_KIND_LABELS[k]}</option>)}
              </NativeSelect>
              <Input aria-label="Round title" value={r.title} onChange={(e) => setRound(i, { title: e.target.value })} placeholder="Title" />
              <Input aria-label="Minutes" type="number" min={1} max={60} value={r.minutes} onChange={(e) => setRound(i, { minutes: Number(e.target.value) })} />
              {r.kind === "technical" || r.kind === "behavioral" ? (
                <Input aria-label="Question count" type="number" min={1} max={12} value={r.question_count ?? ""} placeholder="Qs" onChange={(e) => setRound(i, { question_count: e.target.value ? Number(e.target.value) : null })} />
              ) : r.kind === "coding" ? (
                <NativeSelect aria-label="Language" value={r.language ?? "python"} onChange={(e) => setRound(i, { language: e.target.value })}>
                  <option value="python">Python</option>
                  <option value="javascript">JavaScript</option>
                  <option value="typescript">TypeScript</option>
                </NativeSelect>
              ) : (
                <span />
              )}
              <Button variant="ghost" size="icon-sm" aria-label="Remove round" onClick={() => setT({ ...t, rounds: t.rounds.filter((_, j) => j !== i) })}>
                <Trash2 className="size-4" />
              </Button>
              {r.kind === "technical" && (
                <div className="flex flex-wrap gap-1.5 md:col-span-5" role="group" aria-label="Topics">
                  {topics.map((tp) => {
                    const on = r.topics.includes(tp.key);
                    return (
                      <button
                        key={tp.key}
                        type="button"
                        aria-pressed={on}
                        onClick={() => setRound(i, { topics: on ? r.topics.filter((x) => x !== tp.key) : [...r.topics, tp.key] })}
                        className={cn("rounded-full border px-2 py-0.5 text-xs", on ? "border-primary bg-accent text-accent-foreground" : "text-muted-foreground hover:bg-muted")}
                      >
                        {tp.label}
                      </button>
                    );
                  })}
                </div>
              )}
            </li>
          ))}
        </ol>
        <Button variant="outline" size="sm" className="mt-2" onClick={() => setT({ ...t, rounds: [...t.rounds, { kind: "technical", title: "Technical", minutes: 10, topics: [], question_count: 2 }] })}>
          <Plus className="size-3.5" /> Add round
        </Button>
      </div>

      {weightTopics.length > 0 && (
        <div className="mt-6">
          <p className="text-sm font-medium">Scoring weights (optional)</p>
          <p className="mb-2 text-xs text-muted-foreground">Relative importance of each topic in the overall score. Leave blank to weight by time spent.</p>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-6">
            {weightTopics.map((k) => (
              <label key={k} className="space-y-1 text-xs">
                <span className="text-muted-foreground">{catalog.topics.find((x) => x.key === k)?.label ?? k}</span>
                <Input
                  type="number"
                  min={0}
                  max={100}
                  value={t.scoring_weights[k] ?? ""}
                  onChange={(e) => {
                    const w = { ...t.scoring_weights };
                    if (e.target.value === "") delete w[k];
                    else w[k] = Number(e.target.value);
                    setT({ ...t, scoring_weights: w });
                  }}
                />
              </label>
            ))}
          </div>
        </div>
      )}

      <div className="mt-6 space-y-1.5">
        <Label htmlFor="tj">Job description / role notes (optional)</Label>
        <Textarea id="tj" rows={4} value={t.jd_text} onChange={(e) => setT({ ...t, jd_text: e.target.value })} placeholder="Used to prioritise topics for every candidate taking this interview." />
      </div>
      <div className="mt-6 flex justify-end gap-2">
        <Button variant="ghost" onClick={onCancel}>Cancel</Button>
        <Button onClick={save} disabled={busy || !t.name.trim() || t.rounds.length === 0}>
          {busy && <Spinner />} Save template
        </Button>
      </div>
    </section>
  );
}
