import type { CodingProblemView } from "@intervue/types";
import { Database } from "lucide-react";

function Value({ v }: { v: unknown }) {
  return <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs break-all">{JSON.stringify(v)}</code>;
}

export function ProblemPanel({ problem, isSql }: { problem: CodingProblemView; isSql: boolean }) {
  return (
    <div className="space-y-5 text-sm">
      <div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span>{isSql ? "SQL challenge" : "Coding problem"}</span>
          <span>·</span>
          <span>{["", "Easy", "Medium", "Hard"][problem.difficulty] ?? "Medium"}</span>
        </div>
        <h2 className="mt-1 text-lg font-semibold">{problem.title}</h2>
      </div>
      <p className="leading-relaxed whitespace-pre-wrap">{problem.statement}</p>

      {problem.function_name && (
        <p className="text-xs text-muted-foreground">
          Implement <code className="font-mono text-foreground">{problem.function_name}</code>. Your function is called with the test inputs below plus{" "}
          {problem.hidden_test_count ?? 0} hidden tests on submit.
        </p>
      )}

      {problem.constraints && problem.constraints.length > 0 && (
        <section>
          <h3 className="mb-1.5 font-medium">Constraints</h3>
          <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
            {problem.constraints.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        </section>
      )}

      {problem.examples && problem.examples.length > 0 && (
        <section className="space-y-2">
          <h3 className="font-medium">Example</h3>
          {problem.examples.map((e, i) => (
            <div key={i} className="space-y-1 rounded-lg bg-muted/60 p-3 font-mono text-xs">
              <p className="break-all"><span className="text-muted-foreground">Input: </span>{e.input}</p>
              <p className="break-all"><span className="text-muted-foreground">Output: </span>{e.output}</p>
            </div>
          ))}
        </section>
      )}

      {problem.visible_tests && problem.visible_tests.length > 0 && (
        <section className="space-y-2">
          <h3 className="font-medium">Visible tests</h3>
          {problem.visible_tests.map((t) => (
            <div key={t.name} className="rounded-lg border p-3 text-xs">
              <p className="font-medium">{t.name}</p>
              <p className="mt-1">args: <Value v={t.args} /></p>
              <p className="mt-1">expected: <Value v={t.expected} /></p>
            </div>
          ))}
        </section>
      )}

      {problem.schema && (
        <section className="space-y-3">
          <h3 className="flex items-center gap-1.5 font-medium">
            <Database className="size-4" /> Database schema
          </h3>
          <p className="text-muted-foreground">{problem.schema.description}</p>
          {problem.schema.tables.map((t) => (
            <div key={t.name} className="overflow-hidden rounded-lg border">
              <div className="flex items-center justify-between bg-muted/60 px-3 py-1.5 text-xs">
                <span className="font-mono font-medium">{t.name}</span>
                <span className="text-muted-foreground">{t.row_count} rows</span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr>
                      {t.columns.map((c) => (
                        <th key={c} className="px-2 py-1 text-left font-mono font-medium">
                          {c}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="text-muted-foreground">
                    {t.sample.map((row, i) => (
                      <tr key={i} className="border-t">
                        {t.columns.map((c) => (
                          <td key={c} className="px-2 py-1 font-mono whitespace-nowrap">
                            {String(row[c])}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </section>
      )}
    </div>
  );
}
