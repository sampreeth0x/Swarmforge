# Nebius setup guide

## Token Factory (LLM)

1. Sign up at [console.nebius.com](https://console.nebius.com) → **Token Factory**.
2. Create an API key.
3. Put it in `.env`:

```
NEBIUS_TOKEN_FACTORY_API_KEY=nfkey-...
SWARMFORGE_MODE=tokenfactory
```

4. Verify model access:

```bash
swarmforge list-models
```

Look for the Nemotron models:

- `nemotron-3-super-120b-a12b` (planner / judge / merger)
- `nemotron-3-nano-30b-a3b` (workers / verifier)

If the exact IDs differ on your account, copy the live ones from `list-models`
into `SWARMFORGE_MODEL_PLANNER` / `SWARMFORGE_MODEL_WORKER`.

## NVIDIA NIM fallback

Get a key at [build.nvidia.com](https://build.nvidia.com), set `NVIDIA_NIM_API_KEY`,
and switch `SWARMFORGE_MODE=nim`. Same OpenAI-compatible protocol, same models.

## Contree sandboxes (cloud mode, optional)

The local backend needs no credentials. For cloud isolation:

1. Enable **Sandboxes (Contree)** in the Nebius console; create an IAM token and
   note your project ID.
2. `.env`:

```
SWARMFORGE_SANDBOX_BACKEND=contree
NEBIUS_IAM_TOKEN=
NEBIUS_PROJECT_ID=
```

3. Beta note: Contree caps concurrent operations (~50) — keep `SWARMFORGE_WORKERS`
   ≤ 4 in cloud mode.

## Recording a run for offline replay

```
SWARMFORGE_RECORD_DIR=mock/recorded swarmforge mission "add CSV export"
```

Scenario YAML lands in `mock/recorded/` — set `SWARMFORGE_MODE=mock` and the demo
replays without network access.