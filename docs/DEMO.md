# Demo guide

## 1. Zero-key demo (mock mode)

```bash
uv sync
npm --prefix apps/dashboard install && npm --prefix apps/dashboard run build
swarmforge serve          # open http://127.0.0.1:8000
```

In the dashboard: type *"Add dark mode support to the fixture repo"* (or anything),
set workers to 2–4, press **Launch swarm →**. The swarm graph fills in as the
planner, workers, verifier, judge and merger act; the event stream shows every
tool call; the diff tab shows the merged branch when the mission lands (~15 s).

CLI equivalent: `swarmforge demo`.

## 2. Real-model demo (Nebius Token Factory)

```bash
cp .env.example .env      # fill NEBIUS_TOKEN_FACTORY_API_KEY
swarmforge list-models    # sanity-check Nemotron IDs
SWARMFORGE_MODE=tokenfactory swarmforge serve
```

Launch a mission on the `examples/target-repo` fixture, then on your own repo
(`SWARMFORGE_TARGET_REPO` / config). Record it:

```bash
SWARMFORGE_RECORD_DIR=mock/recorded swarmforge mission "..."
```

## 3. Video capture checklist

- [ ] Dashboard open at `127.0.0.1:8000`, dark theme, full screen
- [ ] Launch mission live — narrate planner → workers racing → verdict
- [ ] Click a worker node mid-run: tool calls streaming in event pane
- [ ] Show merged diff + verdict card + usage bar at the end
- [ ] Cut to terminal: `swarmforge demo` completing in mock mode (Wi-Fi fallback)
- [ ] Show `scripts/e2e_mock.py` passing in CI (GitHub Actions page)

See [VIDEO_SCRIPT.md](VIDEO_SCRIPT.md) for the ≤3-minute script.