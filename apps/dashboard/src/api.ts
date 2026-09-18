import type { Mission, MissionSummary } from "./types";

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return (await res.json()) as T;
}

export const api = {
  async health(): Promise<{ ok: boolean; mode: string }> {
    return json(await fetch("/api/health"));
  },
  async listMissions(): Promise<MissionSummary[]> {
    return json(await fetch("/api/missions"));
  },
  async getMission(id: string): Promise<Mission> {
    return json(await fetch(`/api/missions/${id}`));
  },
  async createMission(request: string, workers: number): Promise<Mission> {
    return json(
      await fetch("/api/missions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ request, workers }),
      }),
    );
  },
  async missionDiff(id: string): Promise<{ diff: string; branch: string }> {
    return json(await fetch(`/api/missions/${id}/diff`));
  },
};

export function eventUrl(missionId: string): string {
  return `/api/missions/${missionId}/events`;
}