"""SwarmForge CLI — `swarmforge serve | mission | demo | list-models`."""

import argparse
import asyncio
import sys


def _run_mission_cli(request: str) -> int:
    """Run one mission to completion in the current terminal."""
    from swarmforge.config import load_config
    from swarmforge.events.bus import EventBus
    from swarmforge.orchestrator.orchestrator import MissionRunner
    from swarmforge.store.db import Store

    cfg = load_config()
    store = Store(cfg.db_path)
    bus = EventBus(store)
    mid = store.create_mission(request, cfg.workers)
    print(f"mission {mid} — mode={cfg.mode} workers={cfg.workers}")

    async def watch() -> None:
        q = bus.subscribe(mid)
        try:
            while True:
                ev = await q.get()
                payload = {k: v for k, v in ev.payload.items()
                           if k in ("tool", "title", "branch", "summary", "candidate_id",
                                    "passed", "merged", "dropped", "error")}
                print(f"  [{ev.kind.value}] {ev.agent_id or '-'} {payload}")
                if ev.kind.value in ("mission.done", "mission.failed"):
                    return
        finally:
            bus.unsubscribe(q, mid)

    runner = MissionRunner(cfg, store, bus)

    async def _main() -> None:
        await asyncio.gather(runner.run_mission(mid), watch())

    try:
        asyncio.run(_main())
    finally:
        m = store.get_mission(mid)
        print(f"mission {mid} -> status={m['status']} branch={m['result_branch']} "
              f"error={m['error']}")
    return 0 if store.get_mission(mid)["status"] == "done" else 1


def _list_models() -> int:
    from swarmforge.config import load_config
    from swarmforge.llm.openai_compat import OpenAICompatProvider

    cfg = load_config()
    provider = OpenAICompatProvider(cfg.llm_url, cfg.llm_api_key, name=cfg.mode)
    try:
        models = asyncio.run(provider.list_models())
    except Exception as exc:  # noqa: BLE001
        print(f"could not list models from {cfg.llm_url}: {exc}", file=sys.stderr)
        return 1
    nemotron = [m for m in models if "nemotron" in m.lower()]
    print(f"{len(models)} models available; Nemotron models:")
    for m in nemotron:
        print(f"  {m}")
    if not nemotron:
        print("  (no Nemotron models found — check your provider account access)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="swarmforge", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("serve", help="start the API + dashboard server")
    p_mission = sub.add_parser("mission", help="run a mission from the command line")
    p_mission.add_argument("request", help="the feature request text")
    sub.add_parser("demo", help="run the built-in demo mission in mock mode")
    sub.add_parser("list-models", help="list models available on the configured LLM provider")

    args = parser.parse_args(argv)

    if args.command == "serve":
        from swarmforge.api.app import run_server

        run_server()
        return 0
    if args.command == "mission":
        return _run_mission_cli(args.request)
    if args.command == "demo":
        return _run_mission_cli(
            "Add dark mode support to the fixture repo: a dark theme stylesheet, "
            "theme validation in render_page, tests, and README documentation.")
    if args.command == "list-models":
        return _list_models()
    if args.command == "list-models":
        print("[todo] list-models not wired yet", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
