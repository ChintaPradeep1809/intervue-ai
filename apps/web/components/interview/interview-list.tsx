"use client";

import { INTERVIEW_TYPE_LABELS } from "@intervue/config";
import type { InterviewSummary } from "@intervue/types";
import { ArrowRight, Clock, FileBarChart2, Play, Trash2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { LinkButton, ScoreText, StatusBadge } from "@/components/shared/primitives";
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
import { api, errorMessage } from "@/lib/api";
import { formatDate } from "@/lib/format";

export function primaryAction(iv: InterviewSummary): { href: string; label: string; icon: React.ComponentType<{ className?: string }> } {
  if (iv.status === "completed") return { href: `/interviews/${iv.id}/report`, label: "View report", icon: FileBarChart2 };
  if (iv.status === "in_progress") return { href: `/interviews/${iv.id}/room`, label: "Resume", icon: Play };
  if (iv.status === "evaluating") return { href: `/interviews/${iv.id}/report`, label: "Report pending", icon: Clock };
  if (iv.status === "planned") return { href: `/interviews/${iv.id}/setup`, label: "Start", icon: Play };
  return { href: `/interviews/${iv.id}`, label: "Open", icon: ArrowRight };
}

export function InterviewList({ items, onDeleted }: { items: InterviewSummary[]; onDeleted?: (id: string) => void }) {
  const [pending, setPending] = useState<InterviewSummary | null>(null);
  return (
    <>
      <ul className="divide-y rounded-xl border bg-card">
        {items.map((iv) => {
          const a = primaryAction(iv);
          return (
            <li key={iv.id} className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center">
              <div className="min-w-0 flex-1">
                <Link href={`/interviews/${iv.id}`} className="block truncate font-medium hover:underline">
                  {iv.title}
                </Link>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {INTERVIEW_TYPE_LABELS[iv.interview_type] ?? iv.interview_type} · {iv.duration_minutes} min · {iv.difficulty} · {formatDate(iv.completed_at ?? iv.created_at)}
                  {iv.is_demo && " · Demo"}
                </p>
              </div>
              <div className="flex items-center gap-3">
                <StatusBadge status={iv.status} />
                <span className="w-10 text-right text-sm">
                  <ScoreText score={iv.overall_score} />
                </span>
                <LinkButton href={a.href} variant={iv.status === "completed" ? "outline" : "default"} size="sm">
                  <a.icon className="size-3.5" /> {a.label}
                </LinkButton>
                {onDeleted && iv.status !== "in_progress" && (
                  <Button variant="ghost" size="icon-sm" aria-label={`Delete ${iv.title}`} onClick={() => setPending(iv)}>
                    <Trash2 className="size-4 text-muted-foreground" />
                  </Button>
                )}
              </div>
            </li>
          );
        })}
      </ul>
      <AlertDialog open={!!pending} onOpenChange={(o) => !o && setPending(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this interview?</AlertDialogTitle>
            <AlertDialogDescription>
              The transcript, code, screen snapshots, scores and report will be permanently deleted. This can&apos;t be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={async () => {
                if (!pending) return;
                try {
                  await api(`/interviews/${pending.id}`, { method: "DELETE" });
                  toast.success("Interview deleted");
                  onDeleted?.(pending.id);
                } catch (e) {
                  toast.error(errorMessage(e));
                } finally {
                  setPending(null);
                }
              }}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
