"use client";

import "@xyflow/react/dist/style.css";

import type { DesignGraph } from "@intervue/types";
import {
  addEdge,
  Background,
  type Connection,
  Controls,
  type Edge,
  Handle,
  type Node,
  type NodeProps,
  Position,
  ReactFlow,
  useEdgesState,
  useNodesState,
} from "@xyflow/react";
import { Activity, Box, Cloud, Cpu, Database, Globe, HardDrive, Layers, Monitor, Radio, Search, Server, Shuffle, Timer, Workflow } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

export const COMPONENTS: { kind: string; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
  { kind: "s3", label: "S3", icon: HardDrive },
  { kind: "glue", label: "Glue", icon: Workflow },
  { kind: "lambda", label: "Lambda", icon: Cpu },
  { kind: "kinesis", label: "Kinesis", icon: Radio },
  { kind: "kafka", label: "Kafka", icon: Shuffle },
  { kind: "redshift", label: "Redshift", icon: Database },
  { kind: "athena", label: "Athena", icon: Search },
  { kind: "airflow", label: "Airflow", icon: Timer },
  { kind: "api", label: "API", icon: Globe },
  { kind: "database", label: "Database", icon: Database },
  { kind: "application", label: "Application", icon: Monitor },
  { kind: "queue", label: "Queue", icon: Layers },
  { kind: "cache", label: "Cache", icon: Box },
  { kind: "service", label: "Service", icon: Server },
  { kind: "monitoring", label: "Monitoring", icon: Activity },
  { kind: "cloud", label: "External", icon: Cloud },
];
const ICONS = Object.fromEntries(COMPONENTS.map((c) => [c.kind, c.icon]));

type CompNode = Node<{ label: string; kind: string }, "component">;

function ComponentNode({ data, selected }: NodeProps<CompNode>) {
  const Icon = ICONS[data.kind] ?? Box;
  return (
    <div className={cn("flex items-center gap-2 rounded-lg border bg-card px-3 py-2 text-xs font-medium text-card-foreground shadow-sm", selected && "ring-2 ring-primary")}>
      <Handle type="target" position={Position.Left} className="!size-2 !bg-primary" />
      <Icon className="size-4 text-primary" />
      {data.label}
      <Handle type="source" position={Position.Right} className="!size-2 !bg-primary" />
    </div>
  );
}

const nodeTypes = { component: ComponentNode };

export function DesignCanvas({ interviewId, readOnly }: { interviewId: string; readOnly?: boolean }) {
  const [nodes, setNodes, onNodesChange] = useNodesState<CompNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [notes, setNotes] = useState("");
  const [saved, setSaved] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const loaded = useRef(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const seq = useRef(0);

  useEffect(() => {
    api<{ graph: DesignGraph | null }>(`/interviews/${interviewId}/design`)
      .then(({ graph }) => {
        if (graph) {
          setNodes(graph.nodes.map((n, i) => ({ id: n.id, type: "component", position: { x: 40 + (i % 4) * 170, y: 40 + Math.floor(i / 4) * 110 }, data: { label: n.label, kind: n.kind } })));
          setEdges(graph.edges.map((e) => ({ id: `${e.source}-${e.target}`, source: e.source, target: e.target, label: e.label, animated: true })));
          setNotes(graph.notes ?? "");
        }
      })
      .catch(() => undefined)
      .finally(() => {
        loaded.current = true;
      });
  }, [interviewId, setNodes, setEdges]);

  const save = useCallback(
    (n: CompNode[], e: Edge[], text: string) => {
      if (!loaded.current || readOnly) return;
      if (timer.current) clearTimeout(timer.current);
      setSaved("saving");
      timer.current = setTimeout(async () => {
        try {
          await api(`/interviews/${interviewId}/design`, {
            method: "PUT",
            body: {
              nodes: n.map((x) => ({ id: x.id, kind: x.data.kind, label: x.data.label })),
              edges: e.map((x) => ({ source: x.source, target: x.target, label: typeof x.label === "string" ? x.label : "" })),
              notes: text,
            },
          });
          setSaved("saved");
        } catch {
          setSaved("error");
        }
      }, 1000);
    },
    [interviewId, readOnly],
  );

  useEffect(() => {
    save(nodes, edges, notes);
    // only structural changes matter; positions are cosmetic
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes.length, edges, notes]);

  const onConnect = useCallback((c: Connection) => setEdges((es) => addEdge({ ...c, animated: true }, es)), [setEdges]);

  function add(kind: string, label: string) {
    const count = nodes.filter((n) => n.data.kind === kind).length;
    seq.current += 1;
    const id = `${kind}-${nodes.length}-${seq.current}`;
    setNodes((ns) => [
      ...ns,
      { id, type: "component", position: { x: 60 + (ns.length % 4) * 170, y: 50 + Math.floor(ns.length / 4) * 110 }, data: { kind, label: count ? `${label} ${count + 1}` : label } },
    ]);
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      {!readOnly && (
        <div className="flex flex-wrap gap-1.5 border-b p-2" role="toolbar" aria-label="Architecture components">
          {COMPONENTS.map((c) => (
            <button
              key={c.kind}
              onClick={() => add(c.kind, c.label)}
              className="inline-flex items-center gap-1 rounded-md border bg-background px-2 py-1 text-xs hover:bg-muted"
              aria-label={`Add ${c.label}`}
            >
              <c.icon className="size-3.5" /> {c.label}
            </button>
          ))}
        </div>
      )}
      <div className="relative min-h-0 flex-1">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          nodeTypes={nodeTypes}
          fitView
          deleteKeyCode={readOnly ? null : ["Backspace", "Delete"]}
          nodesConnectable={!readOnly}
          nodesDraggable={!readOnly}
          proOptions={{ hideAttribution: true }}
        >
          <Background gap={20} size={1} />
          <Controls showInteractive={false} />
        </ReactFlow>
        {nodes.length === 0 && (
          <p className="pointer-events-none absolute inset-0 grid place-items-center text-sm text-muted-foreground">
            Add components from the toolbar, then drag from one handle to another to connect them.
          </p>
        )}
        <span className="absolute top-2 right-2 rounded bg-background/80 px-2 py-0.5 text-[11px] text-muted-foreground">
          {saved === "saving" ? "Saving…" : saved === "saved" ? "Saved" : saved === "error" ? "Not saved — retrying on next change" : ""}
        </span>
      </div>
      <div className="border-t p-2">
        <Textarea
          aria-label="Design notes"
          rows={2}
          placeholder="Notes: data volumes, SLAs, failure handling, security, cost…"
          value={notes}
          readOnly={readOnly}
          onChange={(e) => setNotes(e.target.value)}
          className="resize-none text-sm"
        />
      </div>
    </div>
  );
}
