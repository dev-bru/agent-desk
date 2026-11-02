"""Show the desk commands in the terminal."""

import argparse

from agent_desk.bus import Bus, MemoryBus
from agent_desk.runner import list_dead_letters, replay


def main(argv: list[str] | None = None, *, bus: Bus | None = None) -> int:
    """Read a command and show help for the current project stage."""
    parser = argparse.ArgumentParser(prog="agent-desk")
    commands = parser.add_subparsers(dest="command")
    for name in ("simulate", "run", "approve", "eval"):
        commands.add_parser(name)
    dlq = commands.add_parser("dlq").add_subparsers(dest="action", required=True)
    dlq.add_parser("list")
    replay_parser = dlq.add_parser("replay")
    replay_parser.add_argument("offset", type=int)
    args = parser.parse_args(argv)
    if args.command == "dlq":
        bus = bus if bus is not None else MemoryBus()
        records = list_dead_letters(bus)
        if args.action == "list":
            for record in records:
                print(record.offset, record.key, record.headers["dlq-reason"].decode("utf-8"))
        else:
            record = next((record for record in records if record.offset == args.offset), None)
            if record is None:
                parser.error("No dead letter at that offset")
            replay(bus, record)
            print(f"Replayed {record.key}")
        return 0
    if args.command:
        parser.error(f"{args.command} is implemented in a later feature")
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
