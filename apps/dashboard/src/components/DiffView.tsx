import { useEffect, useState } from "react";
import { api } from "../api";
import type { Candidate, Mission } from "../types";

export function DiffView({ mission, candidate }: { mission: Mission | null; candidate: Candidate | null }) {
  const [merged, setMerged] = useState<{ diff: string; branch: string } | null>(null);

  useEffect(() => {
    if (candidate || mission?.status !== "done") return setMerged(null);
    let alive = true;
    api.missionDiff(mission.id).then((d) => alive && setMerged(d)).catch(() => {});
    return () => {
      alive = false;
    };
  }, [mission?.id, mission?.status, candidate]);

  const diff = candidate ? candidate.diff : (merged?.diff ?? "");
  const label = candidate
    ? `candidate ${candidate.id} · ${candidate.commit_message || candidate.task_id}`
    : merged?.branch
      ? `merged → ${merged.branch}`
      : "merged diff";

  return (
    <div className="h-full flex flex-col">
      <div className="px-3 py-1.5 text-[11px] font-mono text-slate-400 border-b border-slate-800 shrink-0">
        {label}
      </div>
      <div className="flex-1 overflow-auto font-mono text-[11px] leading-snug p-2">
        {!diff && <div className="text-slate-600 p-4">no diff yet…</div>}
        {diff.split("\n").map((line, i) => (
          <div
            key={i}
            className={
              line.startsWith("+++") || line.startsWith("---")
                ? "text-slate-500"
                : line.startsWith("@@")
                  ? "text-cyan-400 bg-cyan-950/40"
                  : line.startsWith("+")
                    ? "text-emerald-300 bg-emerald-950/40"
                    : line.startsWith("-")
                      ? "text-rose-300 bg-rose-950/40"
                      : line.startsWith("diff --git")
                        ? "text-slate-200 font-semibold mt-2"
                        : "text-slate-400"
            }
          >
            {line || " "}
          </div>
        ))}
      </div>
    </div>
  );
}