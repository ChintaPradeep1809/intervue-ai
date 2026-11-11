"use client";

import type { ExecutionResult } from "@intervue/types";
import { AlertTriangle, CheckCircle2, Clock, Play, RotateCcw, Send, Sparkles, XCircle } from "lucide-react";
import dynamic from "next/dynamic";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { Spinner } from "@/components/shared/primitives";
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
import { cn } from "@/lib/utils";

// Monaco is large: load it only when a coding round starts.
const Editor = dynamic(() => import("@monaco-editor/react").then((m) => m.default), {
  ssr: false,
  loading: () => (
    <div className="grid h-full place-items-center text-sm text-muted-foreground">
      <Spinner />
    </div>
  ),
});

const LANG_LABEL: Record<string, string> = { python: "Python", javascript: "JavaScript", typescript: "TypeScript", sql: "SQL" };

interface MonacoEditor {
  getAction: (id: string) => { run: () => Promise<void> } | null;
}

export function CodeWorkspace({
  interviewId,
  starter,
  initialCode,
  initialLanguage,
  isSql,
  submitted,
  onCodeChange,
  onSubmitted,
}: {
  interviewId: string;
  starter: Record<string, string>;
  initialCode: string;
  initialLanguage: string;
  isSql: boolean;
  submitted: boolean;
  onCodeChange: (code: string, language: string) => void;
  onSubmitted: () => void;
}) {
  const [language, setLanguage] = useState(initialLanguage);
  const [code, setCode] = useState(initialCode || starter[initialLanguage] || "");
  const [result, setResult] = useState<ExecutionResult | null>(null);
  const [running, setRunning] = useState<"run" | "submit" | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [tab, setTab] = useState<"tests" | "output">("tests");
  const editorRef = useRef<MonacoEditor | null>(null);
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null);
  const languages = isSql ? ["sql"] : Object.keys(starter).filter((l) => l !== "sql");

  useEffect(() => () => {
    if (debounce.current) clearTimeout(debounce.current);
  }, []);

  function change(v: string | undefined) {
    const next = v ?? "";
    setCode(next);
    if (debounce.current) clearTimeout(debounce.current);
    debounce.current = setTimeout(() => onCodeChange(next, language), 1500);
  }

  async function execute(kind: "run" | "submit") {
    setRunning(kind);
    setConfirm(false);
    try {
      const r = await api<ExecutionResult>(`/interviews/${interviewId}/code/${kind}`, { body: { code, language } });
      setResult(r);
      setTab(r.status === "error" || r.status === "timeout" ? "output" : "tests");
      if (kind === "submit") {
        toast.success(`Submitted — ${r.passed}/${r.total} checks passed. The interviewer will now review your code.`);
        onSubmitted();
      }
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setRunning(null);
    }
  }

  const statusIcon =
    result?.status === "passed" ? <CheckCircle2 className="size-4 text-success" /> : result?.status === "timeout" ? <Clock className="size-4 text-warning" /> : result ? <XCircle className="size-4 text-destructive" /> : null;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b px-3 py-2">
        <div className="flex items-center gap-2">
          {languages.length > 1 ? (
            <select
              aria-label="Language"
              value={language}
              disabled={submitted}
              onChange={(e) => {
                const l = e.target.value;
                setLanguage(l);
                if (!code.trim() || code === starter[language]) setCode(starter[l] ?? "");
              }}
              className="h-8 rounded-md border bg-background px-2 text-sm"
            >
              {languages.map((l) => (
                <option key={l} value={l}>
                  {LANG_LABEL[l] ?? l}
                </option>
              ))}
            </select>
          ) : (
            <span className="rounded-md bg-muted px-2 py-1 text-xs font-medium">{LANG_LABEL[language]}</span>
          )}
          <Button
            variant="ghost"
            size="sm"
            disabled={submitted || language === "python" || language === "sql"}
            title={language === "python" || language === "sql" ? "Formatting is available for JavaScript and TypeScript" : "Format code"}
            onClick={() => void editorRef.current?.getAction("editor.action.formatDocument")?.run()}
          >
            <Sparkles className="size-3.5" /> Format
          </Button>
          <Button variant="ghost" size="sm" disabled={submitted} onClick={() => change(starter[language] ?? "")}>
            <RotateCcw className="size-3.5" /> Reset
          </Button>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" disabled={!!running || submitted} onClick={() => execute("run")}>
            {running === "run" ? <Spinner /> : <Play className="size-3.5" />} Run
          </Button>
          <Button size="sm" disabled={!!running || submitted} onClick={() => setConfirm(true)}>
            {running === "submit" ? <Spinner /> : <Send className="size-3.5" />} {submitted ? "Submitted" : "Submit"}
          </Button>
        </div>
      </div>
      <div className="min-h-0 flex-1">
        <Editor
          height="100%"
          language={language}
          value={code}
          onChange={change}
          onMount={(editor) => {
            editorRef.current = editor as unknown as MonacoEditor;
          }}
          theme="vs-dark"
          options={{
            minimap: { enabled: false },
            fontSize: 14,
            fontLigatures: true,
            scrollBeyondLastLine: false,
            tabSize: language === "python" ? 4 : 2,
            readOnly: submitted,
            automaticLayout: true,
            padding: { top: 12 },
            ariaLabel: "Code editor",
          }}
        />
      </div>
      <div className="h-[34%] min-h-36 overflow-hidden border-t bg-background">
        <div className="flex items-center gap-3 border-b px-3 py-1.5 text-xs">
          {(["tests", "output"] as const).map((t) => (
            <button key={t} onClick={() => setTab(t)} className={cn("rounded px-2 py-1 font-medium", tab === t ? "bg-muted" : "text-muted-foreground")}>
              {t === "tests" ? (isSql ? "Result" : "Tests") : "Output"}
            </button>
          ))}
          {result && (
            <span className="ml-auto flex items-center gap-1.5 text-muted-foreground">
              {statusIcon}
              {result.kind === "submit" ? "Submission" : "Run"}: {result.passed}/{result.total} passed · {result.runtime_ms} ms
              {result.backend === "local" && <span className="text-warning-foreground">· dev sandbox</span>}
            </span>
          )}
        </div>
        <div className="h-[calc(100%-33px)] overflow-auto p-3 font-mono text-xs">
          {!result ? (
            <p className="font-sans text-muted-foreground">Run your code to see results. Runs use the visible tests; Submit adds hidden tests.</p>
          ) : tab === "output" ? (
            <div className="space-y-2">
              {result.error && (
                <p className="flex gap-1.5 text-destructive">
                  <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
                  <span className="whitespace-pre-wrap">{result.error}</span>
                </p>
              )}
              <pre className="whitespace-pre-wrap text-muted-foreground">
                {[result.stdout, ...result.outcomes.map((o) => o.stdout).filter(Boolean)].filter(Boolean).join("\n") || "(no output)"}
              </pre>
            </div>
          ) : isSql && result.columns ? (
            <div className="space-y-2">
              <ul className="flex flex-wrap gap-3 font-sans">
                {result.outcomes.map((o) => (
                  <li key={o.name} className="flex items-center gap-1">
                    {o.passed ? <CheckCircle2 className="size-3.5 text-success" /> : <XCircle className="size-3.5 text-destructive" />} {o.name}
                    {!o.passed && o.expected !== undefined && o.expected !== null && <span className="text-muted-foreground">(expected {String(o.expected)}, got {String(o.actual)})</span>}
                  </li>
                ))}
              </ul>
              <table className="w-full">
                <thead>
                  <tr>
                    {result.columns.map((c) => (
                      <th key={c} className="border-b px-2 py-1 text-left">
                        {c}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.rows?.map((r, i) => (
                    <tr key={i} className="border-b border-border/50">
                      {r.map((v, j) => (
                        <td key={j} className="px-2 py-1 whitespace-nowrap">
                          {String(v)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
              {result.truncated && <p className="font-sans text-muted-foreground">Showing the first 100 rows.</p>}
            </div>
          ) : (
            <ul className="space-y-2">
              {result.error && <li className="text-destructive">{result.error}</li>}
              {result.outcomes.map((o) => (
                <li key={o.name} className="rounded border p-2">
                  <p className="flex items-center gap-1.5 font-sans font-medium">
                    {o.passed ? <CheckCircle2 className="size-3.5 text-success" /> : <XCircle className="size-3.5 text-destructive" />}
                    {o.name} {o.hidden && <span className="font-normal text-muted-foreground">(hidden)</span>}
                    <span className="ml-auto font-normal text-muted-foreground">{o.ms} ms</span>
                  </p>
                  {!o.hidden && !o.passed && (
                    <div className="mt-1 space-y-0.5 text-muted-foreground">
                      <p>expected: {JSON.stringify(o.expected)}</p>
                      <p>actual: {o.error ? <span className="text-destructive">{o.error}</span> : JSON.stringify(o.actual)}</p>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
      <AlertDialog open={confirm} onOpenChange={setConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Submit your final solution?</AlertDialogTitle>
            <AlertDialogDescription>Hidden tests will run and the interviewer will ask you about your implementation. You can&apos;t edit the code afterwards.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep working</AlertDialogCancel>
            <AlertDialogAction onClick={() => execute("submit")}>Submit</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
