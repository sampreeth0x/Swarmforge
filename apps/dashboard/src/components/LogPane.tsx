import { useEffect, useRef } from "react";
import type { SseEvent } from "../types";

const KIND_COLOR: Record<string, string> = {
  "tool.called": "text-cyan-300",
  "tool.result": "text-cyan-500",
  "agent.step": "text-slate-500",
  "task.claimed": "text-violet-300",
  "candidate.ready": "text-emerald-300",
  "tests.passed": "text-emerald-300",
  "tests.failed": "text-rose-300",
  verdict: "text-fuchsia-300",
  "merge.conflict": "text-amber-300",
  "merge.done": "text-emerald-300",
  "mission.done": "text-emerald-400",
  "mission.failed": "text-rose-400",
  usage: "text-slate-600",
};

function summary(ev: SseEvent): string {
  const p = ev.payload ?? {};
  for (const key of ["tool", "title", "summary", "branch", "candidate_id", "error"]) {
    if (p[key] !== undefined && p[key] !== null && p[key] !== "") return String(p[key]);
  }
  if (p.passed !== undefined) return p.passed ? "passed ✓" : "failed ✗";
  const extra = Object.keys(p).filter((k) => k !== "agent_id");
  return extra.length ? JSON.stringify(Object.fromEntries(extra.map((k) => [k, p[k]]))) : "";
}

export function LogPane({ events }: { events: SseEvent[] }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.scrollTo({ top: ref.current.scrollHeight });
  }, [events.length]);

  return (
    <div ref={ref} className="h-full overflow-y-auto font-mono text-[11px] leading-relaxed p-2">
      {events.length === 0 && <div className="text-slate-600 p-4">waiting for events…</div>}
      {events.map((ev) => (
        <div key={ev.id} className="flex gap-2 whitespace-pre-wrap">
          <span className="text-slate-600 shrink-0">
            {new Date(ev.ts).toLocaleTimeString([], { hour12: false })}
          </span>
          <span className={`shrink-0 w-32 truncate ${KIND_COLOR[ev.kind] ?? "text-slate-400"}`}>
            {ev.kind}
          </span>
          <span className="shrink-0 w-24 truncate text-slate-500">{ev.agent_id ?? "—"}</span>
          <span className="text-slate-300 break-all">{summary(ev)}</span>
        </div>
      ))}
    </div>
  );
}