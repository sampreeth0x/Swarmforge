# SwarmForge — Architecture

## The problem with one big prompt

Asking a single LLM "implement this feature" fails at scale: no isolation between
attempts, no way to compare alternatives, and a broken edit silently corrupts the
workspace. SwarmForge instead treats coding like a CI pipeline with agents as
build workers: **fork, race, verify, merge** — the same model that makes distributed
builds reliable.

## Core abstractions

### 1. `LLMProvider` protocol (`llm/`)

```python
async def chat(messages, *, tools, model, temperature, max_tokens,
               role, session) -> LLMResponse
```

Implementations:

- **`OpenAICompatProvider`** — plain `httpx` against Nebius Token Factory
  (`api.tokenfactory.nebius.com/v1`) or NVIDIA NIM. Full control of tool-call
  parsing and per-call usage capture (tokens + cost via published per-Mtok prices).
- **`MockProvider`** — YAML scenarios matched by role / prompt-substring
  (specificity-scored), with per-mission step cursors. The whole hackathon demo
  runs with zero API keys on the exact same orchestration code path.
- **`RecordingProvider`** — wraps any real provider and saves each role's
  transcript as replayable scenario YAML (`SWARMFORGE_RECORD_DIR=...`).

### 2. `SandboxBackend` protocol (`sandbox/`)

`create / exec / read_file / write_file / list_files / fork / commit / diff /
export_patch / teardown`.

- **`LocalWorktreeBackend`** — one git worktree per sandbox on branch
  `swarm/<label>-<sid>`; `fork` branches from the sibling worktree. Zero
  credentials, works on Windows (autocrlf off, longpaths on, CREATE_NO_WINDOW).
- **`ContreeBackend`** (Day 8) — Nebius Contree VM sandboxes; fork = re-run on a
  state UUID. The orchestrator only sees the protocol.

### 3. Agent tool loop (`agents/base.py`)

`chat → tool_calls → ToolRegistry.dispatch → tool messages → repeat` until
`stop_reason == "stop"` or `max_steps`. Tools are plain Python callables with
JSON-schema specs (`fs`, `run_command`, `git_*`, `fork_sandbox`,
`submit_candidate`). Every dispatch publishes `tool.called` / `tool.result` events
and usage is accounted per agent (`USAGE` events + `agents` table).

### 4. Event backbone (`events/`, `store/`)

SQLite (WAL) is the single source of truth: missions, tasks, candidates, agents,
events. `EventBus` persists then fans out to per-mission queues. The SSE endpoint
replays the persisted snapshot after `Last-Event-ID`, then streams live with 15 s
heartbeats — refreshing the dashboard mid-mission replays the full history in
order. Non-terminal missions are rehydrated on server start (claimed/running
tasks reset to `ready`), so a crashed run resumes.

## Orchestration state machines

Mission: `planning → spawning → executing → verifying → judging → merging → done`
(`→ failed` at any point, with the error recorded and published).

Task: `pending → ready (deps done) → claimed (atomic UPDATE) → running → done | retrying | failed`.
Claims are atomic SQLite updates inside a lock — verified by a 10-thread test
where every thread claims a distinct task.

### Planner

One constrained call (Nemotron Super) → strict JSON plan (`id`, `title`,
`instructions`, `acceptance_criteria`, `depends_on`, `files_touched`). A pure
validator checks duplicate ids, unknown deps, and cycles (DFS); one repair
round-trip re-asks the model on invalid output.

### Worker pool

Dependency-wave promotion (task goes `ready` when all deps are `done`), bounded
parallelism (`max_workers`), per-worker `submit_candidate` events closing the
task. On a worker that finishes without submitting: retry with a fresh sandbox
(2 attempts), then fail the task — the mission continues with the survivors.

### Verification

Each candidate patch is applied with `git apply --3way` into a *fresh* sandbox
from `main`, then the repo's real test suite runs. The verifier agent additionally
checks acceptance criteria against the captured pytest output. Empty diffs fail
fast; unparseable verifier output falls back to pytest ground truth.

### Judge

Single passing candidate → shortcut verdict. Multiple → the judge agent ranks
with rationale; hallucinated candidate ids are rejected, and the fallback is
"highest-ranked passing candidate".

### Merge arena

Fresh sandbox at `main`; winning patches applied one at a time with
`git apply --3way`, tests re-run after **every** apply. Conflict or red tests →
the merger agent gets the failing hunks + output with fs/exec/git tools; if it
can't repair, the candidate is dropped. Because merging is git-layer logic, it
works identically over local worktrees and Contree cloud states (which expose no
merge API). Result: branch `swarm/arena-<mission>-<sha>` — main never goes red.

## Dashboard

Vite + React + TS + Tailwind v4, served same-origin from the API (mounted
`dist/`). `@xyflow/react` swarm graph laid out with dagre (planner → workers →
verifier → judge → merger; active workers pulse). Event stream pane colors every
kind; diff view shows the merged result or any candidate's patch; verdict card
shows the judge ranking; usage bar aggregates tokens/cost per role.

## Testing strategy

- **Unit**: state machine, DAG validation, atomic claim (10 threads), sandbox
  lifecycle + fork isolation + path-traversal guard, mock determinism.
- **Integration**: full mock mission asserting the merged branch contains the
  expected change; API CRUD; SSE replay against a real uvicorn instance
  (ASGITransport buffers whole bodies, so streaming needs a real socket).
- **E2E**: `scripts/e2e_mock.py` boots the server, runs a mission to merge, exits
  0/1 — runs in CI on every push.

## Windows notes

No `shell=True`; argv lists + `CREATE_NO_WINDOW`; process trees killed with
`taskkill /F /T` on timeout; `errors="replace"` on decode; git always invoked
with `-c core.autocrlf=false -c core.longpaths=true`; fixture repo forces LF.