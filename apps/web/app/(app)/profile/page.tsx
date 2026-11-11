"use client";

import type { Catalog } from "@intervue/types";
import { FileText } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { ErrorState, LoadingBlock, NativeSelect, PageHeader, Spinner } from "@/components/shared/primitives";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, errorMessage } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useSession } from "@/lib/session";
import { useApi } from "@/lib/use-api";

interface Profile {
  full_name: string;
  email: string;
  experience_years: number | null;
  target_role: string | null;
  headline: string;
  location: string;
  resumes: { id: string; filename: string; size_bytes: number; created_at: string }[];
}

export default function ProfilePage() {
  const router = useRouter();
  const { refresh, setUser, user } = useSession();
  const { data, error, loading, reload } = useApi<Profile>("/me/profile");
  const { data: catalog } = useApi<Catalog>("/catalog");
  const [form, setForm] = useState({ full_name: "", experience_years: "", target_role: "", headline: "", location: "" });
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => {
    if (!data) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- initialise the form from loaded data
    setForm({
      full_name: data.full_name,
      experience_years: data.experience_years?.toString() ?? "",
      target_role: data.target_role ?? "",
      headline: data.headline,
      location: data.location,
    });
  }, [data]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await api("/me/profile", {
        method: "PUT",
        body: { ...form, experience_years: form.experience_years === "" ? null : Number(form.experience_years), target_role: form.target_role || null },
      });
      await refresh();
      toast.success("Profile saved");
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function openResume(id: string) {
    try {
      const { url } = await api<{ url: string }>(`/documents/resume/${id}/url`);
      window.open(url, "_blank", "noopener");
    } catch (e) {
      toast.error(errorMessage(e));
    }
  }

  if (loading) return <LoadingBlock rows={3} />;
  if (error || !data) return <ErrorState message={error?.message ?? "Could not load profile."} onRetry={reload} />;

  return (
    <>
      <PageHeader title="Profile" description="Your details calibrate interview difficulty and role focus." />
      <div className="grid gap-8 lg:grid-cols-[1.4fr_1fr]">
        <form onSubmit={save} className="space-y-4 rounded-xl border bg-card p-6">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="fn">Full name</Label>
              <Input id="fn" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="em">Email</Label>
              <Input id="em" value={data.email} disabled />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="yx">Years of experience</Label>
              <Input id="yx" type="number" min={0} max={50} step={0.5} value={form.experience_years} onChange={(e) => setForm({ ...form, experience_years: e.target.value })} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="tr">Target role</Label>
              <NativeSelect id="tr" value={form.target_role} onChange={(e) => setForm({ ...form, target_role: e.target.value })}>
                <option value="">Not set</option>
                {catalog?.roles.map((r) => (
                  <option key={r.key} value={r.key}>
                    {r.title}
                  </option>
                ))}
              </NativeSelect>
            </div>
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="hl">Headline</Label>
              <Input id="hl" value={form.headline} onChange={(e) => setForm({ ...form, headline: e.target.value })} placeholder="e.g. Data engineer focused on AWS pipelines" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="lc">Location</Label>
              <Input id="lc" value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} />
            </div>
          </div>
          <div className="flex justify-end">
            <Button type="submit" disabled={busy}>
              {busy && <Spinner />} Save changes
            </Button>
          </div>
        </form>

        <div className="space-y-6">
          <section className="rounded-xl border bg-card p-5">
            <h2 className="mb-3 text-sm font-medium">Resumes</h2>
            {data.resumes.length ? (
              <ul className="space-y-2">
                {data.resumes.map((r) => (
                  <li key={r.id} className="flex items-center gap-3 text-sm">
                    <FileText className="size-4 text-muted-foreground" />
                    <button onClick={() => openResume(r.id)} className="min-w-0 flex-1 truncate text-left hover:underline">
                      {r.filename}
                    </button>
                    <span className="text-xs text-muted-foreground">{formatDate(r.created_at)}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">No resume uploaded. Add one when creating an interview.</p>
            )}
          </section>
          {user?.role !== "super_admin" && (
            <section className="rounded-xl border border-destructive/30 p-5">
              <h2 className="text-sm font-medium">Delete account</h2>
              <p className="mt-1 text-sm text-muted-foreground">Permanently delete your account, resumes, interviews, transcripts and reports.</p>
              <Button variant="destructive" size="sm" className="mt-3" onClick={() => setConfirmDelete(true)}>
                Delete my account
              </Button>
            </section>
          )}
        </div>
      </div>
      <AlertDialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete your account?</AlertDialogTitle>
            <AlertDialogDescription>All of your data will be permanently removed. This can&apos;t be undone.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={async () => {
                try {
                  await api("/me", { method: "DELETE" });
                  setUser(null);
                  router.replace("/");
                } catch (e) {
                  toast.error(errorMessage(e));
                }
              }}
            >
              Delete everything
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
