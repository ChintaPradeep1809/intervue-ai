"use client";

import { CheckCircle2, Code2, XCircle } from "lucide-react";
import dynamic from "next/dynamic";
import { useParams } from "next/navigation";

import { EmptyState, ErrorState, LinkButton, LoadingBlock, PageHeader } from "@/components/shared/primitives";
import { formatDateTime } from "@/lib/format";
import { useApi } from "@/lib/use-api";

const Editor = dynamic(() => import("@monaco-editor/react").then((m) => m.default), { ssr: false });

interface CodeSessionView {
  id: string;
  problem_id: string;
  title: string;
  statement: string;
  language: string;
  is_sql: boolean;
  code: string;
  submitted_at: string | null;
  executions: { kind: string; status: string; passed: number; total: number; runtime_ms: number; created_at: string; backend: string }[];
}

/** Read-only review of the candidate's coding sessions: final code and every run/submission. */
export default function CodingReviewPage() {
  const { id } = useParams<{ id: string }>();
  const { data, error, loading, reload } = useApi<{ sessions: CodeSessionView[] }>(`/interviews/${id}/code`);
  return (
    <>
      <PageHeader
        eyebrow="Coding review"
        title="Code & executions"
        description="Your final code for each coding round and every run and submission."
        actions={<LinkButton href={`/interviews/${id}/report`} variant="outline" className="h-9">Back to report</LinkButton>}
      />
      {loading ? (
        <LoadingBlock rows={3} />
      ) : error ? (
        <ErrorState message={error.message} onRetry={reload} />
      ) : !data?.sessions.length ? (
        <EmptyState icon={Code2} title="No code yet" description="Coding rounds you complete will appear here." />
      ) : (
        <div className="space-y-8">
          {data.sessions.map((s) => (
            <section key={s.id} className="overflow-hidden rounded-xl border bg-card">
              <div className="border-b p-4">
                <h2 className="font-semibold">{s.title}</h2>
                <p className="mt-1 text-sm text-muted-foreground">{s.statement}</p>
              </div>
              <div className="grid lg:grid-cols-[1.4fr_1fr]">
                <div className="h-80 border-r">
                  <Editor height="100%" language={s.language} value={s.code} theme="vs-dark" options={{ readOnly: true, minimap: { enabled: false }, fontSize: 13, scrollBeyondLastLine: false }} />
                </div>
                <ol className="max-h-80 divide-y overflow-y-auto text-sm">
                  {s.executions.map((e, i) => (
                    <li key={i} className="flex items-center gap-3 px-4 py-2.5">
                      {e.status === "passed" ? <CheckCircle2 className="size-4 text-success" /> : <XCircle className="size-4 text-destructive" />}
                      <div className="flex-1">
                        <p className="font-medium capitalize">{e.kind}</p>
                        <p className="text-xs text-muted-foreground">{formatDateTime(e.created_at)}</p>
                      </div>
                      <span className="tabular">
                        {e.passed}/{e.total}
                      </span>
                      <span className="w-16 text-right text-xs text-muted-foreground tabular">{e.runtime_ms} ms</span>
                    </li>
                  ))}
                </ol>
              </div>
            </section>
          ))}
        </div>
      )}
    </>
  );
}
