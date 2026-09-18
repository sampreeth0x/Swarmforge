# SwarmForge ⚡

> A self-organizing swarm of NVIDIA Nemotron coding agents that fork, test, and merge
> code across parallel sandboxes — shipping features while you sleep.

**Nebius x NVIDIA Global AI Hackathon** — Coding & Agentic Engineering track.

## What it does

Submit a feature request. SwarmForge takes it from there:

1. **Planner** (Nemotron 3 Super) decomposes the request into a dependency DAG of subtasks
2. **Swarm of workers** (Nemotron 3 Nano, 1–8) each implement a subtask in its *own*
   isolated sandbox — and can `fork_sandbox` mid-task to race two approaches in parallel
3. **Verifier** applies every candidate patch in a fresh sandbox and runs the repo's
   *real* test suite against it — no vibes-based completion
4. **Judge** (Nemotron 3 Super) ranks the passing candidates with rationale
5. **Merge arena** applies winning patches one at a time (`git apply --3way`),
   re-running tests after *every* apply; a merger agent repairs conflicts agentic-ally,
   and candidates that can't be made to work are dropped — main never goes red
6. Everything — every tool call, every test run, every token — streams live to a
   mission-control dashboard with a swarm graph, event stream, and diff viewer

**Why it matters:** one orchestrator instead of one mega-prompt. Workers race in
isolated forks, the losers die cheaply, and only test-passing code reaches main.
The same pipeline works on local git worktrees *and* Nebius Contree cloud sandboxes.

## Quickstart (zero API keys)

```bash
git clone <this-repo> && cd swarmforge
uv sync                                  # python 3.12 via uv
npm --prefix apps/dashboard install      # once, for the dashboard build
npm --prefix apps/dashboard run build    # produces apps/dashboard/dist
swarmforge demo                          # full mission, mock mode, ~15s
swarmforge serve                         # dashboard at http://127.0.0.1:8000
```

`swarmforge demo` runs the entire pipeline — planner → 2 racing workers → verification
→ judge → merge arena — using scripted mock LLM scenarios. Zero credentials, fully
deterministic, and it's the same code path the real models take.

## Real models (Nebius Token Factory)

```bash
cp .env.example .env            # add your NEBIUS_TOKEN_FACTORY_API_KEY
swarmforge list-models          # verifies Nemotron model IDs on your account
swarmforge serve                # launch missions from the dashboard
swarmforge mission "add CSV export to the reports page"
```

- **Planner / judge / merger:** `nemotron-3-super-120b-a12b`
- **Workers / verifier:** `nemotron-3-nano-30b-a3b`
- Models and provider are env-configurable (`SWARMFORGE_MODE=tokenfactory|nim|mock`);
  NVIDIA NIM (`integrate.api.nvidia.com`) works as a drop-in fallback provider.

### Recording a run for offline replay

```bash
SWARMFORGE_RECORD_DIR=mock/recorded swarmforge mission "..."
```

One real run becomes replayable mock scenarios — the demo works even if the venue
Wi-Fi dies.

## Architecture

```
POST /api/missions ──▶ MissionRunner
                          │
            ┌─────────────▼──────────────┐
            │  Planner (Super)  ── plan DAG (JSON, repair round)
            ├────────────────────────────┤
            │  WorkerPool (Nano ×N)      │   each worker:
            │   atomic SQLite task claim │   own sandbox → tool loop →
            │   dependency waves         │   fork? → submit_candidate
            ├────────────────────────────┤
            │  Verifier  fresh sandbox per candidate, real pytest
            ├────────────────────────────┤
            │  Judge (Super)  rank passing candidates
            ├────────────────────────────┤
            │  Merge arena  apply --3way + re-test per patch,
            │               agentic conflict repair
            └─────────────┬──────────────┘
                          ▼
             swarm/<mission> branch + MISSION_DONE
```

Every agent action publishes an event (SQLite-backed `EventBus`) that fans out over
**SSE** — snapshot-first with `Last-Event-ID` replay, so a dashboard refresh
mid-mission never loses the plot. Kill the server mid-mission and it **resumes on
restart**. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Sandboxes

| Backend | Isolation | Fork model | Credentials |
|---|---|---|---|
| `local` (default) | git worktrees | branch from sibling worktree | none |
| `contree` | Nebius VM microVMs | state UUID re-run | Nebius IAM token |

The merge arena is backend-agnostic git-layer logic, so candidates from either
backend merge identically. `SWARMFORGE_SANDBOX_BACKEND=contree` switches backends
(see [docs/NEBIUS_SETUP.md](docs/NEBIUS_SETUP.md)).

## Dashboard

Mission-control UI (Vite + React + Tailwind): live swarm graph (forks fan out from
the planner, merge edges light up as candidates win), streaming event log with every
tool call, plan checklist, per-candidate diffs, judge verdict card, and a per-role
token/cost bar. Same-origin with the API at `/`.

## Testing

```bash
uv run pytest -q                 # 19 unit + integration tests, incl. Windows
uv run python scripts/e2e_mock.py  # boots the server, runs a mission to merge (CI)
```

Full-mission e2e: plan → parallel workers → verification → judge → merge arena,
asserting the merged branch actually contains the change (`static/dark.css`).

## Repo layout

```
src/swarmforge/       llm/ (providers + mock + recording) · sandbox/ (worktree backend)
                      agents/ (tool loop, fs/exec/git/swarm tools, prompts)
                      orchestrator/ (planner, workers, verifier, judge, merger)
                      events/ (bus + SSE) · store/ (SQLite WAL) · api/ (FastAPI)
apps/dashboard/       mission-control UI
mock/scenarios/       scripted YAML runs (dark-mode demo, defaults)
examples/target-repo/ the tiny repo the swarm modifies in demos
scripts/e2e_mock.py   boots server + runs a mission end-to-end
```

## License

MIT — see [LICENSE](LICENSE).