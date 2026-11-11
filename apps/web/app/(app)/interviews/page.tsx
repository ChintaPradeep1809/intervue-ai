"use client";

import type { InterviewSummary } from "@intervue/types";
import { ListChecks, PlusCircle } from "lucide-react";
import { useState } from "react";

import { InterviewList } from "@/components/interview/interview-list";
import { EmptyState, ErrorState, LinkButton, LoadingBlock, PageHeader } from "@/components/shared/primitives";
import { cn } from "@/lib/utils";
import { useApi } from "@/lib/use-api";

const FILTERS = [
  { key: "all", label: "All" },
  { key: "planned", label: "Not started" },
  { key: "in_progress", label: "In progress" },
  { key: "completed", label: "Completed" },
];

export default function InterviewsPage() {
  const { data, error, loading, reload, setData } = useApi<{ items: InterviewSummary[] }>("/interviews?limit=100");
  const [filter, setFilter] = useState("all");
  const items = (data?.items ?? []).filter((i) => filter === "all" || i.status === filter);
  return (
    <>
      <PageHeader
        title="Interviews"
        description="Every interview you've planned, started or completed."
        actions={
          <LinkButton href="/interviews/new" className="h-9">
            <PlusCircle className="size-4" /> New interview
          </LinkButton>
        }
      />
      <div className="mb-4 flex gap-1" role="tablist" aria-label="Filter interviews">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            role="tab"
            aria-selected={filter === f.key}
            onClick={() => setFilter(f.key)}
            className={cn("rounded-full px-3 py-1 text-sm", filter === f.key ? "bg-foreground text-background" : "text-muted-foreground hover:bg-muted")}
          >
            {f.label}
          </button>
        ))}
      </div>
      {loading ? (
        <LoadingBlock rows={5} />
      ) : error ? (
        <ErrorState message={error.message} onRetry={reload} />
      ) : items.length === 0 ? (
        <EmptyState icon={ListChecks} title="Nothing here yet" description="Interviews you create will appear here." action={<LinkButton href="/interviews/new">Create interview</LinkButton>} />
      ) : (
        <InterviewList items={items} onDeleted={(id) => setData({ items: (data?.items ?? []).filter((i) => i.id !== id) })} />
      )}
    </>
  );
}
