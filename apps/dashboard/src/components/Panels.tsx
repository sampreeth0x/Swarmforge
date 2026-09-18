import type { Candidate, Mission, Task } from "../types";

const TASK_BADGE: Record<string, string> = {
  pending: "bg-slate-700 text-slate-300",
  ready: "bg-sky-800 text-sky-200",
  claimed: "bg-indigo-800 text-indigo-200",
  running: "bg-cyan-700 text-cyan-100 animate-pulse",
  retrying: "bg-amber-700 text-amber-100",
  done: "bg-emerald-800 text-emerald-200",
  failed: "bg-rose-800 text-rose-200",
};

export function TaskList({ tasks }: { tasks: Task[] }) {
  return (
    <div className="space-y-1.5">
      {tasks.map((t) => (
        <div key={t.id} className="flex items-start gap-2">
          <span className={`shrink-0 mt-0.5 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase
                            ${TASK_BADGE[t.status] ?? "bg-slate-700"}`}>
            {t.status}
          </span>
          <div className="min-w-0">
            <div className="text-xs text-slate-200 leading-snug">{t.title}</div>
            <div className="text-[10px] font-mono text-slate-500">
              {t.id} · attempts {t.attempts}
            </div>
          </div>
        </div>
      ))}
      {tasks.length === 0 && <div className="text-xs text-slate-600">no plan yet…</div>}
    </div>
  );
}

export interface RankingEntry {
  candidate_id: string;
  rank?: number;
  reason?: string;
  winner?: boolean;
  [k: string]: unknown;
}

export function VerdictCard({
  mission,
  ranking,
}: {
  mission: Mission | null;
  ranking: RankingEntry[];
}) {
  const candidates = mission?.candidates ?? [];
  return (
    <div className="space-y-2">
      {ranking.length === 0 && (
        <div className="text-xs text-slate-600">verdict arrives after verification…</div>
      )}
      {ranking
        .slice()
        .sort((a, b) => (a.rank ?? 99) - (b.rank ?? 99))
        .map((r) => {
          const c = candidates.find((x) => x.id === r.candidate_id);
          return (
            <div
              key={r.candidate_id}
              className={`rounded-lg border px-3 py-2 ${
                r.winner
                  ? "border-emerald-500 bg-emerald-950/40"
                  : "border-slate-700 bg-slate-900/60"
              }`}
            >
              <div className="flex items-center gap-2 text-xs">
                {r.winner && <span>🏆</span>}
                <span className="font-mono text-slate-300">{r.candidate_id}</span>
                {r.rank != null && <span className="text-slate-500">#{r.rank}</span>}
                {c && (
                  <span
                    className={`ml-auto rounded px-1.5 text-[10px] font-semibold ${
                      c.tests_passed
                        ? "bg-emerald-800 text-emerald-200"
                        : "bg-rose-800 text-rose-200"
                    }`}
                  >
                    {c.tests_passed ? "tests ✓" : "tests ✗"}
                  </span>
                )}
              </div>
              {c && (
                <div className="mt-1 text-[11px] text-slate-400 truncate">
                  {c.commit_message || c.task_id}
                </div>
              )}
              {r.reason && <div className="mt-1 text-[11px] text-slate-300">{r.reason}</div>}
            </div>
          );
        })}
    </div>
  );
}

export function CandidateList({
  candidates,
  selected,
  onSelect,
}: {
  candidates: Candidate[];
  selected: string | null;
  onSelect: (c: Candidate) => void;
}) {
  return (
    <div className="space-y-1">
      {candidates.map((c) => (
        <button
          key={c.id}
          onClick={() => onSelect(c)}
          className={`w-full text-left rounded px-2 py-1.5 border text-xs flex items-center gap-2
            ${
              selected === c.id
                ? "border-cyan-500 bg-cyan-950/40"
                : "border-slate-800 bg-slate-900/40 hover:border-slate-600"
            }`}
        >
          <span
            className={`rounded px-1 text-[10px] font-semibold shrink-0 ${
              c.tests_passed ? "bg-emerald-800 text-emerald-200" : "bg-rose-800 text-rose-200"
            }`}
          >
            {c.tests_passed ? "✓" : "✗"}
          </span>
          <span className="truncate text-slate-300">{c.commit_message || c.task_id}</span>
          <span className="ml-auto shrink-0 font-mono text-[10px] text-slate-500">{c.id}</span>
        </button>
      ))}
      {candidates.length === 0 && (
        <div className="text-xs text-slate-600">no candidates yet…</div>
      )}
    </div>
  );
}