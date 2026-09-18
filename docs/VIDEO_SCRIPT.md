# Demo video script (target: 2:45)

**Format:** screen recording, terminal + dashboard. Record at 1080p, dark theme.

---

## [0:00–0:20] Hook — the problem

*(Dashboard idle, empty mission list.)*

> "You ask an AI coding agent to build a feature, and you get one giant prompt
> with no isolation, no alternatives, and no proof it actually works.
>
> This is **SwarmForge** — a self-organizing swarm of NVIDIA Nemotron agents that
> fork, test, and merge code across parallel sandboxes."

## [0:20–0:50] Launch the swarm

*(Type "Add dark mode support to the fixture repo", set workers to 2, click Launch.)*

> "I hand it a feature request. The planner — Nemotron Super — decomposes it into
> a dependency DAG of subtasks. Workers — Nemotron Nano — each grab a task
> atomically from a SQLite queue and get their own isolated sandbox."

*(Swarm graph fills: planner node fans out to worker nodes, edges pulse.)*

> "Watch the graph — every worker is a real git worktree. And any worker can fork
> its own sandbox mid-task to race two approaches."

## [0:50–1:20] The race + verification

*(Event stream scrolling: tool.called write_file, run_command pytest, submit_candidate.)*

> "Every tool call streams live. When workers submit, the verifier doesn't trust
> anyone: it applies each candidate patch to a fresh sandbox and runs the repo's
> real test suite. Failing candidates die here — before they can touch main."

*(tests.failed badge on the weak candidate; tests.passed on the dark-mode one.)*

## [1:20–1:50] Judge + merge arena

*(Verdict card appears; diff tab opens.)*

> "The judge ranks the passing candidates with rationale. Then the merge arena
> applies patches one at a time — re-running the tests after every single apply.
> Conflicts go to a merger agent; if it can't fix it, the candidate is dropped.
> Main never goes red."

*(Mission done badge; merged diff visible.)*

## [1:50–2:20] Under the hood

*(Cut to terminal: `swarmforge demo` finishing; then CI green on GitHub.)*

> "It runs on Nebius Token Factory with Nemotron open models, but the same
> pipeline runs fully offline on scripted mock scenarios — that's this terminal
> demo. Sandboxes are git worktrees locally, Nebius Contree VM sandboxes in the
> cloud — same protocol, same merge arena. And it's all event-sourced in SQLite:
> kill the server mid-mission, and it resumes on restart."

## [2:20–2:45] Close

*(Back on dashboard: usage bar + final graph.)*

> "Parallel attempts, ground-truth verification, agentic merging — SwarmForge
> ships features while you sleep. Built for the Nebius x NVIDIA Global AI
> Hackathon. Thanks for watching!"

*(End card: repo URL + MIT license.)*

---

### Recording notes

- `swarmforge serve` with the dashboard already built; zoom browser to 110%.
- For the live section, use mock mode for reliability; re-record with real
  Nemotron models once the Nebius key is set (preferred if latency is OK).
- Keep the event stream visible the whole time — it's the "alive" signal.