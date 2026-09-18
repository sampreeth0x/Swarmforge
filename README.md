# SwarmForge ⚡

> A self-organizing swarm of NVIDIA Nemotron coding agents that fork, test, and merge
> code across parallel sandboxes — shipping features while you sleep.

**Status:** 🚧 under active construction for the
[Nebius x NVIDIA Global AI Hackathon](https://nebiusglobalaihackathon.devpost.com/)
(Coding & Agentic Engineering track).

## What it does

1. You submit a feature request
2. A **planner** agent (Nemotron 3 Super) decomposes it into a dependency DAG of subtasks
3. A **swarm of worker** agents (Nemotron 3 Nano) each implement a subtask in its own
   isolated sandbox — and can fork its own sandbox mid-task to race approaches
4. A **verifier** runs the repo's real test suite against every candidate
5. A **judge** agent ranks candidates with rationale; a **merge arena** combines winners,
   re-running tests after every merge and resolving conflicts agentically
6. Everything streams live to a mission-control dashboard

## Quickstart (zero API keys)

```bash
uv sync
swarmforge demo      # full mission in mock mode, in seconds
```

## License

MIT — see [LICENSE](LICENSE).