export interface MissionSummary {
  id: string;
  request: string;
  status: string;
  workers: number;
  result_branch?: string | null;
  error?: string | null;
  created_at: string;
}

export interface Task {
  id: string;
  title: string;
  status: string;
  depends_on?: string[];
  attempts: number;
}

export interface Candidate {
  id: string;
  task_id: string;
  agent_id: string;
  diff: string;
  commit_message: string;
  tests_passed: boolean;
  test_output: string;
  verdict?: string | null;
  created_at: string;
}

export interface AgentRow {
  id: string;
  role: string;
  model: string;
  status: string;
  steps: number;
  prompt_tokens: number;
  completion_tokens: number;
  cost_usd: number;
}

export interface Mission extends MissionSummary {
  tasks?: Task[];
  agents?: AgentRow[];
  candidates?: Candidate[];
}

export interface SseEvent {
  id: number;
  kind: string;
  agent_id?: string | null;
  ts: string;
  payload: Record<string, unknown>;
}

export const TERMINAL_STATUSES = ["done", "failed"];

export function isTerminal(status: string): boolean {
  return TERMINAL_STATUSES.includes(status);
}