import { useState } from "react";
import { api } from "../api";
import { usageOf } from "../useMission";
import type { Mission } from "../types";

const ROLE_COLOR: Record<string, string> = {
  planner: "bg-violet-500",
  worker: "bg-cyan-500",
  verifier: "bg-amber-500",
  judge: "bg-fuchsia-500",
  merger: "bg-emerald-500",
};

export function MissionForm({ onCreated }: { onCreated: (id: string) => void }) {
  const [request, setRequest] = useState("");
  const [workers, setWorkers] = useState(2);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = async () => {
    if (!request.trim() || busy) return;
    setBusy(true);
    setError("");
    try {
      const m = await api.createMission(request.trim(), workers);
      setRequest("");
      onCreated(m.id);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-2">
      <textarea
        value={request}
        onChange={(e) => setRequest(e.target.value)}
        placeholder="Describe a feature for the swarm to build…"
        rows={4}
        className="w-full rounded-lg bg-slate-900 border border-slate-700 focus:border-cyan-500
                   outline-none p-2.5 text-sm text-slate-200 placeholder:text-slate-600 resize-none"
      />
      <div className="flex items-center gap-3">
        <label className="text-xs text-slate-400 whitespace-nowrap">
          workers <span className="text-cyan-300 font-mono">{workers}</span>
        </label>
        <input
          type="range"
          min={1}
          max={8}
          value={workers}
          onChange={(e) => setWorkers(Number(e.target.value))}
          className="flex-1 accent-cyan-500"
        />
      </div>
      <button
        onClick={submit}
        disabled={busy || !request.trim()}
        className="w-full rounded-lg bg-cyan-600 hover:bg-cyan-500 disabled:bg-slate-800
                   disabled:text-slate-500 py-2 text-sm font-semibold text-white transition"
      >
        {busy ? "launching…" : "Launch swarm →"}
      </button>
      {error && <div className="text-xs text-rose-400">{error}</div>}
    </div>
  );
}

export function UsageBar({ mission }: { mission: Mission | null }) {
  const u = usageOf(mission);
  const total = Object.values(u.byRole).reduce((a, b) => a + b, 0) || 1;
  return (
    <div className="flex items-center gap-3 text-[11px] font-mono text-slate-400">
      <div className="flex h-1.5 w-40 rounded overflow-hidden bg-slate-800">
        {Object.entries(u.byRole).map(([role, cost]) => (
          <div
            key={role}
            className={ROLE_COLOR[role] ?? "bg-slate-500"}
            style={{ width: `${(cost / total) * 100}%` }}
            title={`${role}: $${cost.toFixed(4)}`}
          />
        ))}
      </div>
      <span>
        {u.promptTokens.toLocaleString()} in / {u.completionTokens.toLocaleString()} out
      </span>
      <span className="text-emerald-400">${u.costUsd.toFixed(4)}</span>
    </div>
  );
}