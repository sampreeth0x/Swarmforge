import dagre from "@dagrejs/dagre";
import "@xyflow/react/dist/style.css";
import { memo } from "react";
import {
  Background,
  Controls,
  Handle,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import type { Mission } from "../types";

const ROLE_STYLE: Record<string, { bg: string; ring: string; icon: string; label: string }> = {
  planner: { bg: "bg-violet-900/70", ring: "ring-violet-400", icon: "🧭", label: "Planner" },
  worker: { bg: "bg-cyan-900/70", ring: "ring-cyan-400", icon: "⚡", label: "Worker" },
  verifier: { bg: "bg-amber-900/70", ring: "ring-amber-400", icon: "🧪", label: "Verifier" },
  judge: { bg: "bg-fuchsia-900/70", ring: "ring-fuchsia-400", icon: "⚖️", label: "Judge" },
  merger: { bg: "bg-emerald-900/70", ring: "ring-emerald-400", icon: "🧬", label: "Merger" },
};

const NodeCard = memo(function NodeCard({ data }: NodeProps) {
  const s = ROLE_STYLE[(data.role as string) ?? "worker"] ?? ROLE_STYLE.worker;
  const status = (data.status as string) ?? "idle";
  const busy = status === "running" || status === "thinking";
  return (
    <div
      className={`rounded-lg ring-2 ${s.ring} ${s.bg} px-3 py-2 min-w-[170px] backdrop-blur
                  ${busy ? "animate-pulse" : ""}`}
    >
      <Handle type="target" position={Position.Left} className="!bg-slate-500" />
      <div className="flex items-center gap-2 text-slate-100 text-xs font-semibold">
        <span>{s.icon}</span>
        <span>{s.label}</span>
        <span className="ml-auto text-[10px] text-slate-400 uppercase tracking-wide">
          {status}
        </span>
      </div>
      <div className="mt-1 text-[10px] font-mono text-slate-400 truncate">{data.id as string}</div>
      <div className="text-[10px] text-slate-300">
        {data.steps as number} steps · {((data.cost as number) || 0).toFixed(4)}$
      </div>
      <Handle type="source" position={Position.Right} className="!bg-slate-500" />
    </div>
  );
});

const nodeTypes = { card: NodeCard };

function layout(nodes: Node[], edges: Edge[]): Node[] {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "LR", nodesep: 36, ranksep: 90 });
  for (const n of nodes) g.setNode(n.id, { width: 190, height: 72 });
  for (const e of edges) g.setEdge(e.source, e.target);
  dagre.layout(g);
  return nodes.map((n) => {
    const p = g.node(n.id);
    return { ...n, position: { x: p.x - 95, y: p.y - 36 } };
  });
}

export function SwarmGraph({ mission, events }: { mission: Mission | null; events: string[] }) {
  const agents = mission?.agents ?? [];
  const kinds = new Set(events);

  const nodes: Node[] = [];
  const edges: Edge[] = [];

  nodes.push({
    id: "planner",
    type: "card",
    position: { x: 0, y: 0 },
    data: { role: "planner", id: "planner", status: "done", steps: 1, cost: 0 },
  });

  const workers = agents.filter((a) => a.role === "worker");
  for (const w of workers) {
    nodes.push({
      id: w.id,
      type: "card",
      position: { x: 0, y: 0 },
      data: { role: "worker", id: w.id, status: w.status, steps: w.steps, cost: w.cost_usd },
    });
    edges.push({ id: `p-${w.id}`, source: "planner", target: w.id, animated: w.status === "running" });
  }

  const stages: { id: string; role: string; trigger: string[] }[] = [
    { id: "verifier", role: "verifier", trigger: ["tests.passed", "tests.failed"] },
    { id: "judge", role: "judge", trigger: ["verdict"] },
    { id: "merger", role: "merger", trigger: ["merge.done", "merge.conflict"] },
  ];
  let prev = "planner";
  for (const st of stages) {
    if (!st.trigger.some((k) => kinds.has(k))) continue;
    nodes.push({
      id: st.id,
      type: "card",
      position: { x: 0, y: 0 },
      data: { role: st.role, id: st.id, status: "done", steps: 0, cost: 0 },
    });
    if (prev === "planner" && workers.length) {
      for (const w of workers) edges.push({ id: `${w.id}-${st.id}`, source: w.id, target: st.id });
    } else {
      edges.push({ id: `${prev}-${st.id}`, source: prev, target: st.id });
    }
    prev = st.id;
  }

  const laidOut = layout(nodes, edges);
  return (
    <ReactFlow
      // Re-fit the viewport when the topology grows (workers/stages appear mid-mission).
      key={`${nodes.length}-${edges.length}`}
      nodes={laidOut}
      edges={edges}
      nodeTypes={nodeTypes}
      fitView
      proOptions={{ hideAttribution: true }}
      className="text-xs"
    >
      <Background color="#1e293b" gap={18} />
      <Controls showInteractive={false} />
    </ReactFlow>
  );
}