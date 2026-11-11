"use client";

import type { Catalog } from "@intervue/types";
import { Download, GitCompare, Search, Users } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { OrgGate } from "@/components/admin/org-gate";
import { EmptyState, ErrorState, LoadingBlock, NativeSelect, PageHeader, ScoreText, StatusBadge } from "@/components/shared/primitives";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { formatDate } from "@/lib/format";
import { useApi } from "@/lib/use-api";

import type { CandidateRow } from "@/components/admin/types";


export default function CandidatesPage() {
  return (
    <OrgGate>
      <Candidates />
    </OrgGate>
  );
}

function Candidates() {
  const router = useRouter();
  const { data: catalog } = useApi<Catalog>("/catalog");
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  const [role, setRole] = useState("");
  const [status, setStatus] = useState("");
  const [review, setReview] = useState("");
  const [minScore, setMinScore] = useState("");
  const [sort, setSort] = useState("date");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<string[]>([]);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(q), 300);
    return () => clearTimeout(t);
  }, [q]);

  const params = new URLSearchParams({ q: debounced, role, status, review, sort, page: String(page) });
  if (minScore) params.set("min_score", minScore);
  const { data, error, loading, reload } = useApi<{ items: CandidateRow[]; total: number; page_size: number }>(`/organization/candidates?${params}`);
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <>
      <PageHeader
        title="Candidates"
        description="Every interview taken through your organization. Scores are AI-assisted — review the evidence before deciding."
        actions={
          <>
            <Button variant="outline" className="h-9" disabled={selected.length < 2} onClick={() => router.push(`/organization/reports?compare=${selected.join(",")}`)}>
              <GitCompare className="size-4" /> Compare ({selected.length})
            </Button>
            <a href="/api/organization/export.csv" className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-primary px-3 text-sm font-medium text-primary-foreground hover:bg-primary/90">
              <Download className="size-4" /> Export CSV
            </a>
          </>
        }
      />
      <div className="mb-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-6">
        <div className="relative lg:col-span-2">
          <Search className="absolute top-2.5 left-2.5 size-4 text-muted-foreground" />
          <Input aria-label="Search candidates" placeholder="Search name or email" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} className="h-9 pl-8" />
        </div>
        <NativeSelect aria-label="Role" value={role} onChange={(e) => { setRole(e.target.value); setPage(1); }}>
          <option value="">All roles</option>
          {catalog?.roles.map((r) => <option key={r.key} value={r.key}>{r.title}</option>)}
        </NativeSelect>
        <NativeSelect aria-label="Status" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
          <option value="">All statuses</option>
          {["planned", "in_progress", "evaluating", "completed", "abandoned"].map((s) => <option key={s} value={s}>{s.replace("_", " ")}</option>)}
        </NativeSelect>
        <NativeSelect aria-label="Review" value={review} onChange={(e) => { setReview(e.target.value); setPage(1); }}>
          <option value="">Any review</option>
          {["pending", "shortlisted", "on_hold", "rejected"].map((s) => <option key={s} value={s}>{s.replace("_", " ")}</option>)}
        </NativeSelect>
        <div className="flex gap-2">
          <Input aria-label="Minimum score" type="number" min={0} max={100} placeholder="Min score" value={minScore} onChange={(e) => { setMinScore(e.target.value); setPage(1); }} className="h-9" />
          <NativeSelect aria-label="Sort" value={sort} onChange={(e) => setSort(e.target.value)}>
            <option value="date">Newest</option>
            <option value="score">Score</option>
            <option value="name">Name</option>
          </NativeSelect>
        </div>
      </div>
      {loading && !data ? (
        <LoadingBlock rows={5} />
      ) : error ? (
        <ErrorState message={error.message} onRetry={reload} />
      ) : !data?.items.length ? (
        <EmptyState icon={Users} title="No candidates match" description="Try different filters, or share an invite link to get started." />
      ) : (
        <>
          <div className="overflow-x-auto rounded-xl border bg-card">
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-muted-foreground">
                <tr className="border-b">
                  <th className="w-10 px-4 py-2.5"><span className="sr-only">Select</span></th>
                  <th className="px-4 py-2.5 font-medium">Candidate</th>
                  <th className="px-4 py-2.5 font-medium">Role</th>
                  <th className="px-4 py-2.5 font-medium">Interview</th>
                  <th className="px-4 py-2.5 font-medium">Score</th>
                  <th className="px-4 py-2.5 font-medium">Status</th>
                  <th className="px-4 py-2.5 font-medium">Review</th>
                  <th className="px-4 py-2.5 font-medium">Date</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((r) => (
                  <tr key={r.interview_id} className="border-b last:border-0 hover:bg-muted/40">
                    <td className="px-4 py-2.5">
                      <Checkbox
                        aria-label={`Select ${r.candidate_name} for comparison`}
                        disabled={r.status !== "completed" || (!selected.includes(r.interview_id) && selected.length >= 4)}
                        checked={selected.includes(r.interview_id)}
                        onCheckedChange={(v) => setSelected((s) => (v ? [...s, r.interview_id] : s.filter((x) => x !== r.interview_id)))}
                      />
                    </td>
                    <td className="px-4 py-2.5">
                      <Link href={`/organization/candidates/${r.candidate_id}`} className="font-medium hover:underline">{r.candidate_name || "—"}</Link>
                      <p className="text-xs text-muted-foreground">{r.candidate_email}</p>
                    </td>
                    <td className="px-4 py-2.5">{r.role}</td>
                    <td className="max-w-56 truncate px-4 py-2.5 text-muted-foreground" title={r.interview}>{r.interview}</td>
                    <td className="px-4 py-2.5"><ScoreText score={r.score} /></td>
                    <td className="px-4 py-2.5"><StatusBadge status={r.status} /></td>
                    <td className="px-4 py-2.5"><StatusBadge status={r.review_status} /></td>
                    <td className="px-4 py-2.5 whitespace-nowrap text-muted-foreground">{formatDate(r.date)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-3 flex items-center justify-between text-sm text-muted-foreground">
            <span>{data.total} interviews</span>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button>
              <span>Page {page} of {pages}</span>
              <Button variant="outline" size="sm" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</Button>
            </div>
          </div>
        </>
      )}
    </>
  );
}
