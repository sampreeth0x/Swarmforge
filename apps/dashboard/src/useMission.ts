import { useCallback, useEffect, useRef, useState } from "react";
import { api, eventUrl } from "./api";
import { isTerminal, type Mission, type MissionSummary, type SseEvent } from "./types";

const MAX_EVENTS = 600;

/** Live mission state: SSE event stream + periodic detail refresh while active. */
export function useMission(missionId: string | null) {
  const [mission, setMission] = useState<Mission | null>(null);
  const [events, setEvents] = useState<SseEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const lastEventAt = useRef(0);

  const refresh = useCallback(async () => {
    if (!missionId) return;
    try {
      setMission(await api.getMission(missionId));
    } catch {
      /* mission may not exist yet */
    }
  }, [missionId]);

  // SSE — EventSource auto-reconnects and replays from Last-Event-ID.
  useEffect(() => {
    setEvents([]);
    setMission(null);
    if (!missionId) return;
    const es = new EventSource(eventUrl(missionId));
    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false);
    es.onmessage = (msg) => {
      try {
        const ev = JSON.parse(msg.data) as SseEvent;
        lastEventAt.current = Date.now();
        setEvents((prev) =>
          prev.length >= MAX_EVENTS ? [...prev.slice(-MAX_EVENTS + 1), ev] : [...prev, ev],
        );
      } catch {
        /* ignore malformed frames */
      }
    };
    return () => es.close();
  }, [missionId]);

  // Poll detail: fast while a mission is live, slow when terminal.
  useEffect(() => {
    if (!missionId) return;
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      if (!alive) return;
      await refresh();
      const m = mission;
      const recentActivity = Date.now() - lastEventAt.current < 10_000;
      const delay = m && isTerminal(m.status) ? 15_000 : recentActivity ? 1_500 : 5_000;
      timer = setTimeout(tick, delay);
    };
    tick();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [missionId, refresh, mission?.status]);

  return { mission, events, connected, refresh };
}

/** Mission list, re-polled while anything is non-terminal. */
export function useMissionList() {
  const [missions, setMissions] = useState<MissionSummary[]>([]);
  const load = useCallback(async () => {
    try {
      setMissions(await api.listMissions());
    } catch {
      /* server not up yet */
    }
  }, []);
  useEffect(() => {
    const timer = setInterval(load, 5_000);
    void load();
    return () => clearInterval(timer);
  }, [load]);
  return missions;
}

export interface Usage {
  promptTokens: number;
  completionTokens: number;
  costUsd: number;
  byRole: Record<string, number>;
}

export function usageOf(mission: Mission | null): Usage {
  const byRole: Record<string, number> = {};
  let promptTokens = 0;
  let completionTokens = 0;
  let costUsd = 0;
  for (const a of mission?.agents ?? []) {
    promptTokens += a.prompt_tokens;
    completionTokens += a.completion_tokens;
    costUsd += a.cost_usd;
    byRole[a.role] = (byRole[a.role] ?? 0) + a.cost_usd;
  }
  return { promptTokens, completionTokens, costUsd, byRole };
}