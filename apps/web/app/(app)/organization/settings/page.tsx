"use client";

import { BookOpen, Building2, Search, Trash2, Upload } from "lucide-react";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { EmptyState, ErrorState, LoadingBlock, NativeSelect, PageHeader, Spinner } from "@/components/shared/primitives";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { api, errorMessage } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useSession } from "@/lib/session";
import { useApi } from "@/lib/use-api";

const KINDS = ["college", "university", "institute", "bootcamp", "company", "other"];

export default function OrgSettingsPage() {
  const { user } = useSession();
  const hasOrg = !!user?.organizations.some((o) => o.role === "admin");
  return hasOrg ? <Settings /> : <CreateOrg />;
}

function CreateOrg() {
  const router = useRouter();
  const { refresh } = useSession();
  const [name, setName] = useState("");
  const [kind, setKind] = useState("college");
  const [busy, setBusy] = useState(false);
  return (
    <>
      <PageHeader title="Create your organization" description="Colleges, institutes and companies use organizations to run interviews at scale." />
      <form
        className="max-w-lg space-y-4 rounded-xl border bg-card p-6"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          try {
            await api("/organizations", { body: { name, kind } });
            await refresh();
            toast.success("Organization created — your 30-day College trial has started.");
            router.push("/organization/interviews");
          } catch (err) {
            toast.error(errorMessage(err));
            setBusy(false);
          }
        }}
      >
        <div className="space-y-1.5">
          <Label htmlFor="on">Organization name</Label>
          <Input id="on" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Sunrise Institute of Technology" required />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="ok">Type</Label>
          <NativeSelect id="ok" value={kind} onChange={(e) => setKind(e.target.value)}>
            {KINDS.map((k) => <option key={k} value={k}>{k[0].toUpperCase() + k.slice(1)}</option>)}
          </NativeSelect>
        </div>
        <Button type="submit" disabled={busy || name.trim().length < 2}>
          {busy && <Spinner />} <Building2 className="size-4" /> Create organization
        </Button>
      </form>
    </>
  );
}

interface OrgData {
  organization: { id: string; name: string; kind: string; settings: { pass_threshold?: number; retention_days?: number } };
  member_role: string;
}

function Settings() {
  const router = useRouter();
  const { refresh } = useSession();
  const { data, error, loading, reload } = useApi<OrgData>("/organization");
  const [form, setForm] = useState<{ name: string; kind: string; pass_threshold: number; retention_days: number } | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmName, setConfirmName] = useState("");

  if (loading) return <LoadingBlock rows={3} />;
  if (error || !data) return <ErrorState message={error?.message ?? "Could not load settings."} onRetry={reload} />;
  const org = data.organization;
  const f = form ?? { name: org.name, kind: org.kind, pass_threshold: org.settings.pass_threshold ?? 60, retention_days: org.settings.retention_days ?? 365 };

  return (
    <>
      <PageHeader title="Organization settings" description={org.name} />
      <div className="grid gap-6 lg:grid-cols-2">
        <form
          className="space-y-4 rounded-xl border bg-card p-6"
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            try {
              await api("/organization/settings", { method: "PUT", body: f });
              await refresh();
              toast.success("Settings saved");
            } catch (err) {
              toast.error(errorMessage(err));
            } finally {
              setBusy(false);
            }
          }}
        >
          <h2 className="font-medium">General</h2>
          <div className="space-y-1.5">
            <Label htmlFor="sn">Name</Label>
            <Input id="sn" value={f.name} onChange={(e) => setForm({ ...f, name: e.target.value })} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="sk">Type</Label>
              <NativeSelect id="sk" value={f.kind} onChange={(e) => setForm({ ...f, kind: e.target.value })}>
                {KINDS.map((k) => <option key={k} value={k}>{k[0].toUpperCase() + k.slice(1)}</option>)}
              </NativeSelect>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="sp">Pass threshold</Label>
              <Input id="sp" type="number" min={0} max={100} value={f.pass_threshold} onChange={(e) => setForm({ ...f, pass_threshold: Number(e.target.value) })} />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="sr">Data retention (days)</Label>
            <Input id="sr" type="number" min={7} max={3650} value={f.retention_days} onChange={(e) => setForm({ ...f, retention_days: Number(e.target.value) })} />
            <p className="text-xs text-muted-foreground">How long candidate transcripts, code and reports are kept.</p>
          </div>
          <Button type="submit" disabled={busy}>{busy && <Spinner />} Save</Button>
        </form>
        <Knowledge />
        <section className="rounded-xl border border-destructive/30 p-6 lg:col-span-2">
          <h2 className="font-medium">Delete organization</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Permanently deletes the organization, its templates, invite links, knowledge base and all interviews taken through it. Type <strong>{org.name}</strong> to confirm.
          </p>
          <div className="mt-3 flex max-w-lg gap-2">
            <Input aria-label="Confirm organization name" value={confirmName} onChange={(e) => setConfirmName(e.target.value)} />
            <Button
              variant="destructive"
              disabled={confirmName !== org.name}
              onClick={async () => {
                try {
                  await api("/organization/delete", { body: { confirm_name: confirmName } });
                  await refresh();
                  toast.success("Organization deleted");
                  router.replace("/dashboard");
                } catch (e) {
                  toast.error(errorMessage(e));
                }
              }}
            >
              <Trash2 className="size-4" /> Delete
            </Button>
          </div>
        </section>
      </div>
    </>
  );
}

function Knowledge() {
  const { data, reload } = useApi<{ items: { id: string; title: string; kind: string; chunks: number; created_at: string }[] }>("/organization/knowledge");
  const [title, setTitle] = useState("");
  const [kind, setKind] = useState("guidelines");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<{ score: number; content: string }[] | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  async function add(file?: File) {
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("title", title || file?.name || "Document");
      fd.append("kind", kind);
      if (file) fd.append("file", file);
      else fd.append("text", text);
      const r = await api<{ chunks: number }>("/organization/knowledge", { body: fd });
      toast.success(`Added — ${r.chunks} chunks indexed`);
      setTitle("");
      setText("");
      reload();
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="space-y-4 rounded-xl border bg-card p-6">
      <div>
        <h2 className="flex items-center gap-2 font-medium"><BookOpen className="size-4" /> Knowledge base</h2>
        <p className="text-sm text-muted-foreground">Guidelines, role descriptions and topic lists are retrieved to shape interviews for your organization.</p>
      </div>
      {data?.items.length ? (
        <ul className="divide-y rounded-lg border text-sm">
          {data.items.map((d) => (
            <li key={d.id} className="flex items-center gap-3 px-3 py-2">
              <span className="min-w-0 flex-1 truncate">{d.title}</span>
              <span className="text-xs text-muted-foreground">{d.kind.replace("_", " ")} · {d.chunks} chunks · {formatDate(d.created_at)}</span>
              <Button variant="ghost" size="icon-xs" aria-label={`Delete ${d.title}`} onClick={async () => { await api(`/organization/knowledge/${d.id}`, { method: "DELETE" }).catch(() => undefined); reload(); }}>
                <Trash2 className="size-3.5" />
              </Button>
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState icon={BookOpen} title="No documents yet" />
      )}
      <div className="grid grid-cols-[1fr_150px] gap-2">
        <Input aria-label="Document title" placeholder="Title" value={title} onChange={(e) => setTitle(e.target.value)} />
        <NativeSelect aria-label="Document type" value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="guidelines">Guidelines</option>
          <option value="role_description">Role description</option>
          <option value="topics">Topics</option>
          <option value="question_bank">Question bank</option>
        </NativeSelect>
      </div>
      <Textarea aria-label="Document text" rows={3} placeholder="Paste text, or upload a PDF/DOCX/TXT" value={text} onChange={(e) => setText(e.target.value)} />
      <div className="flex gap-2">
        <Button size="sm" disabled={busy || text.trim().length < 20} onClick={() => add()}>{busy && <Spinner />} Add text</Button>
        <Button size="sm" variant="outline" disabled={busy} onClick={() => fileRef.current?.click()}><Upload className="size-3.5" /> Upload file</Button>
        <input ref={fileRef} type="file" accept=".pdf,.docx,.txt" className="sr-only" aria-label="Upload knowledge document" onChange={(e) => { const f = e.target.files?.[0]; if (f) void add(f); e.target.value = ""; }} />
      </div>
      <form
        className="flex gap-2 border-t pt-4"
        onSubmit={async (e) => {
          e.preventDefault();
          try {
            setHits((await api<{ items: { score: number; content: string }[] }>("/organization/knowledge/search", { body: { query } })).items);
          } catch (err) {
            toast.error(errorMessage(err));
          }
        }}
      >
        <Input aria-label="Test retrieval" placeholder="Test retrieval, e.g. “SQL expectations”" value={query} onChange={(e) => setQuery(e.target.value)} />
        <Button size="sm" variant="outline" type="submit" disabled={query.length < 2}><Search className="size-3.5" /> Search</Button>
      </form>
      {hits && (
        <ul className="space-y-2 text-xs">
          {hits.length ? hits.map((h, i) => (
            <li key={i} className="rounded-lg bg-muted/50 p-2"><span className="mr-1 font-medium tabular">{h.score.toFixed(2)}</span>{h.content}</li>
          )) : <li className="text-muted-foreground">No relevant passages.</li>}
        </ul>
      )}
    </section>
  );
}
