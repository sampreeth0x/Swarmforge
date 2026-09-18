import { useEffect, useMemo, useState } from "react";
import { DiffView } from "./components/DiffView";
import { LogPane } from "./components/LogPane";
import { MissionForm, UsageBar } from "./components/MissionForm";
import { CandidateList, TaskList, VerdictCard, type RankingEntry } from "./components/Panels";
import { SwarmGraph } from "./components/SwarmGraph";
import { api } from "./api";
import { useMission, useMissionList } from "./useMission";
import type { Candidate } from "./types";

const STATUS_COLOR: Record<string, string> = {
  planning: "text-violet-300",
  spawning: "text-sky-300",
  executing: "text-cyan-300",
  verifying: "text-amber-300",
  judging: "text-fuchsia-300",
  merging: "text-emerald-300",
  done: "text-emerald-400",
  failed: "text-rose-400",
};

export default function App() {
  const missions = useMissionList();
  const [selected, setSelected] = useState<string | null>(null);
  const { mission, events, connected } = useMission(selected);
  const [candidate, setCandidate] = useState<Candidate | null>(null);
  const [mode, setMode] = useState("…");

  useEffect(() => {
    api.health().then((h) => setMode(h.mode)).catch(() => setMode("offline"));
  }, []);

  // Select the newest mission on first load.
  useEffect(() => {
    if (!selected && missions.length) setSelected(missions[0].id);
  }, [missions, selected]);

  useEffect(() => setCandidate(null), [selected]);

  const ranking = useMemo<RankingEntry[]>(() => {
    const ev = [...events].reverse().find((e) => e.kind === "verdict");
    if (ev) return (ev.payload.ranking as RankingEntry[]) ?? [];
    return [];
  }, [events]);

  const tabs = ["log", "diff"] as const;
  const [tab, setTab] = useState<(typeof tabs)[number]>("log");

  return (
    <div className="h-screen flex flex-col bg-slate-950 text-slate-200">
      {/* ── top bar ─────────────────────────────────────────────── */}
      <header className="shrink-0 flex items-center gap-4 px-4 py-2.5 border-b border-slate-800 bg-slate-950">
        <h1 className="text-base font-bold tracking-tight">
          <span className="text-cyan-400">◈</span> SwarmForge
        </h1>
        <span className="rounded-full border border-slate-700 px-2 py-0.5 text-[10px] uppercase tracking-widest text-slate-400">
          {mode}
        </span>
        {mission && (
          <>
            <span className={`text-xs font-semibold uppercase tracking-widest ${STATUS_COLOR[mission.status] ?? ""}`}>
              {mission.status}
            </span>
            {mission.result_branch && (
              <span className="font-mono text-[11px] text-slate-500 truncate">
                {mission.result_branch}
              </span>
            )}
            {mission.error && (
              <span className="text-[11px] text-rose-400 truncate">{mission.error}</span>
            )}
          </>
        )}
        <div className="ml-auto flex items-center gap-3">
          <span
            className={`w-2 h-2 rounded-full ${connected ? "bg-emerald-500" : "bg-slate-600"}`}
            title={connected ? "SSE connected" : "disconnected"}
          />
          <UsageBar mission={mission} />
        </div>
      </header>

      <div className="flex-1 flex min-h-0">
        {/* ── left sidebar ──────────────────────────────────────── */}
        <aside className="shrink-0 w-80 border-r border-slate-800 flex flex-col min-h-0">
          <div className="p-3 border-b border-slate-800">
            <MissionForm onCreated={(id) => setSelected(id)} />
          </div>
          <div className="flex-1 overflow-y-auto p-2 space-y-1">
            {missions.map((m) => (
              <button
                key={m.id}
                onClick={() => setSelected(m.id)}
                className={`w-full text-left rounded-lg px-2.5 py-2 border text-xs ${
                  selected === m.id
                    ? "border-cyan-600 bg-cyan-950/30"
                    : "border-transparent hover:bg-slate-900"
                }`}
              >
                <div className="flex items-center gap-2">
                  <span className={`font-mono text-[10px] text-slate-500`}>{m.id}</span>
                  <span
                    className={`ml-auto text-[10px] uppercase tracking-wide ${STATUS_COLOR[m.status] ?? ""}`}
                  >
                    {m.status}
                  </span>
                </div>
                <div className="mt-0.5 line-clamp-2 text-slate-300 leading-snug">
                  {m.request}
                </div>
              </button>
            ))}
            {missions.length === 0 && (
              <div className="text-xs text-slate-600 p-2">no missions yet — launch one.</div>
            )}
          </div>
        </aside>

        {/* ── main area ─────────────────────────────────────────── */}
        <main className="flex-1 flex flex-col min-h-0">
          <div className="h-[46%] min-h-[220px] border-b border-slate-800 relative">
            <SwarmGraph
              mission={mission}
              events={events.map((e) => e.kind)}
            />
            {mission === null && (
              <div className="absolute inset-0 grid place-items-center text-sm text-slate-600">
                swarm idle — launch a mission
              </div>
            )}
          </div>
          <div className="flex-1 flex flex-col min-h-0">
            <div className="shrink-0 flex gap-1 px-2 pt-1.5 border-b border-slate-800">
              {tabs.map((t) => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  className={`px-3 py-1 text-xs rounded-t ${
                    tab === t
                      ? "bg-slate-900 text-cyan-300 border border-b-0 border-slate-800"
                      : "text-slate-500 hover:text-slate-300"
                  }`}
                >
                  {t === "log" ? `event stream (${events.length})` : "diff"}
                </button>
              ))}
            </div>
            <div className="flex-1 min-h-0 bg-slate-950">
              {tab === "log" ? (
                <LogPane events={events} />
              ) : (
                <DiffView mission={mission} candidate={candidate} />
              )}
            </div>
          </div>
        </main>

        {/* ── right panel ───────────────────────────────────────── */}
        <aside className="shrink-0 w-96 border-l border-slate-800 overflow-y-auto p-3 space-y-5">
          <section>
            <h2 className="text-[11px] font-semibold uppercase tracking-widest text-slate-500 mb-2">
              plan
            </h2>
            <TaskList tasks={mission?.tasks ?? []} />
          </section>
          <section>
            <h2 className="text-[11px] font-semibold uppercase tracking-widest text-slate-500 mb-2">
              candidates
            </h2>
            <CandidateList
              candidates={mission?.candidates ?? []}
              selected={candidate?.id ?? null}
              onSelect={(c) => {
                setCandidate(c);
                setTab("diff");
              }}
            />
          </section>
          <section>
            <h2 className="text-[11px] font-semibold uppercase tracking-widest text-slate-500 mb-2">
              verdict
            </h2>
            <VerdictCard mission={mission} ranking={ranking} />
          </section>
        </aside>
      </div>
    </div>
  );
}