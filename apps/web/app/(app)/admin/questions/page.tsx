"use client";

import { Pencil, Plus, Search, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { RequireRole } from "@/components/layout/app-shell";
import { ErrorState, LoadingBlock, NativeSelect, PageHeader, Spinner } from "@/components/shared/primitives";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { api, errorMessage } from "@/lib/api";
import { useApi } from "@/lib/use-api";

interface Q {
  id?: string;
  bank_key: string;
  topic: string;
  kind: string;
  difficulty: number;
  text: string;
  concepts: { name: string; keywords: string[] }[];
  followups: { type: string; trigger: string; text: string }[];
  roles: string[];
  is_active: boolean;
}

const BLANK: Q = { bank_key: "", topic: "sql", kind: "technical", difficulty: 2, text: "", concepts: [], followups: [], roles: [], is_active: true };

export default function QuestionsPage() {
  return (
    <RequireRole roles={["super_admin"]}>
      <Questions />
    </RequireRole>
  );
}

function Questions() {
  const [topic, setTopic] = useState("");
  const [q, setQ] = useState("");
  const { data, error, loading, reload } = useApi<{ items: Q[]; topics: { key: string; label: string }[] }>(`/admin/questions?topic=${topic}&q=${encodeURIComponent(q)}`);
  const [edit, setEdit] = useState<Q | null>(null);
  return (
    <>
      <PageHeader
        title="Question bank"
        description="Curated questions with expected concepts and follow-ups. The engine selects from these and adapts difficulty."
        actions={<Button className="h-9" onClick={() => setEdit({ ...BLANK })}><Plus className="size-4" /> New question</Button>}
      />
      <div className="mb-4 flex gap-2">
        <div className="relative max-w-sm flex-1">
          <Search className="absolute top-2.5 left-2.5 size-4 text-muted-foreground" />
          <Input aria-label="Search questions" placeholder="Search text" value={q} onChange={(e) => setQ(e.target.value)} className="h-9 pl-8" />
        </div>
        <NativeSelect aria-label="Topic" value={topic} onChange={(e) => setTopic(e.target.value)} className="max-w-56">
          <option value="">All topics</option>
          {data?.topics.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
        </NativeSelect>
      </div>
      {loading && !data ? (
        <LoadingBlock rows={5} />
      ) : error ? (
        <ErrorState message={error.message} onRetry={reload} />
      ) : (
        <>
          <p className="mb-2 text-xs text-muted-foreground">{data?.items.length} questions</p>
          <ul className="divide-y rounded-xl border bg-card">
            {data?.items.map((item) => (
              <li key={item.id} className="flex items-start gap-3 px-4 py-3">
                <div className="min-w-0 flex-1">
                  <p className="text-sm">{item.text}</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {item.topic} · {item.kind} · difficulty {item.difficulty} · {item.concepts.length} concepts · {item.followups.length} follow-ups
                    {item.roles.length ? ` · ${item.roles.join(", ")}` : ""}
                    {!item.is_active && " · inactive"}
                  </p>
                </div>
                <Button variant="ghost" size="icon-sm" aria-label="Edit question" onClick={() => setEdit({ ...item })}><Pencil className="size-4" /></Button>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label="Delete question"
                  onClick={async () => {
                    try {
                      await api(`/admin/questions/${item.id}`, { method: "DELETE" });
                      reload();
                    } catch (e) {
                      toast.error(errorMessage(e));
                    }
                  }}
                >
                  <Trash2 className="size-4" />
                </Button>
              </li>
            ))}
          </ul>
        </>
      )}
      {edit && data && <QuestionDialog value={edit} topics={data.topics} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); reload(); }} />}
    </>
  );
}

function QuestionDialog({ value, topics, onClose, onSaved }: { value: Q; topics: { key: string; label: string }[]; onClose: () => void; onSaved: () => void }) {
  const [q, setQ] = useState(value);
  const [concepts, setConcepts] = useState(value.concepts.map((c) => `${c.name}: ${c.keywords.join(" | ")}`).join("\n"));
  const [followups, setFollowups] = useState(value.followups.map((f) => `${f.type} | ${f.trigger} | ${f.text}`).join("\n"));
  const [busy, setBusy] = useState(false);

  async function save() {
    const body = {
      ...q,
      concepts: concepts.split("\n").filter((l) => l.includes(":")).map((l) => {
        const i = l.indexOf(":");
        return { name: l.slice(0, i).trim(), keywords: l.slice(i + 1).split("|").map((k) => k.trim()).filter(Boolean) };
      }),
      followups: followups.split("\n").filter((l) => l.split("|").length >= 3).map((l) => {
        const [type, trigger, ...rest] = l.split("|");
        return { type: type.trim(), trigger: trigger.trim() || "any", text: rest.join("|").trim() };
      }),
    };
    setBusy(true);
    try {
      if (q.id) await api(`/admin/questions/${q.id}`, { method: "PUT", body });
      else await api("/admin/questions", { body });
      toast.success("Question saved");
      onSaved();
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{q.id ? "Edit question" : "New question"}</DialogTitle>
          <DialogDescription>Concepts drive scoring and follow-ups; keywords are matched in the candidate&apos;s answer.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="col-span-2 space-y-1.5">
              <Label htmlFor="qk">Key</Label>
              <Input id="qk" value={q.bank_key} disabled={!!q.id} onChange={(e) => setQ({ ...q, bank_key: e.target.value })} placeholder="sql-window-dedup" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="qt">Topic</Label>
              <NativeSelect id="qt" value={q.topic} onChange={(e) => setQ({ ...q, topic: e.target.value })}>
                {topics.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
              </NativeSelect>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="qd">Difficulty</Label>
              <NativeSelect id="qd" value={q.difficulty} onChange={(e) => setQ({ ...q, difficulty: Number(e.target.value) })}>
                <option value={1}>1 · Easy</option><option value={2}>2 · Medium</option><option value={3}>3 · Hard</option>
              </NativeSelect>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="qkind">Kind</Label>
              <NativeSelect id="qkind" value={q.kind} onChange={(e) => setQ({ ...q, kind: e.target.value })}>
                {["technical", "behavioral", "introduction", "system_design"].map((k) => <option key={k} value={k}>{k}</option>)}
              </NativeSelect>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="qr">Roles (comma separated, blank = all)</Label>
              <Input id="qr" value={q.roles.join(", ")} onChange={(e) => setQ({ ...q, roles: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })} />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="qx">Question</Label>
            <Textarea id="qx" rows={3} value={q.text} onChange={(e) => setQ({ ...q, text: e.target.value })} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="qc">Expected concepts — one per line: <code>name: keyword | keyword</code></Label>
            <Textarea id="qc" rows={4} className="font-mono text-xs" value={concepts} onChange={(e) => setConcepts(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="qf">Follow-ups — one per line: <code>type | trigger | text</code> (trigger: any, mentioned:concept, missing:concept)</Label>
            <Textarea id="qf" rows={3} className="font-mono text-xs" value={followups} onChange={(e) => setFollowups(e.target.value)} />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <Switch checked={q.is_active} onCheckedChange={(v) => setQ({ ...q, is_active: v })} /> Active
          </label>
        </div>
        <DialogFooter>
          <Button onClick={save} disabled={busy || q.text.length < 10 || q.bank_key.length < 3}>{busy && <Spinner />} Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
