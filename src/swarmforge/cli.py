"""SwarmForge CLI — `swarmforge serve | mission | demo | list-models`."""

import argparse
import sys


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
        print(f"[todo] mission orchestration not wired yet: {args.request!r}", file=sys.stderr)
        return 1
    if args.command == "demo":
        print("[todo] demo mission not wired yet", file=sys.stderr)
        return 1
    if args.command == "list-models":
        print("[todo] list-models not wired yet", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())