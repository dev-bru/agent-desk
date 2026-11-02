"""Show the desk commands in the terminal."""

import argparse
import json

from agent_desk.bus import Bus, MemoryBus
from agent_desk.runner import list_dead_letters, replay
from agent_desk.settings import load_settings
from agent_desk.shop_db import seed


def _run(bus, args):
    """Drain the selected agents, or create a local demo when no bus is supplied."""
    from agent_desk.approver import read_topic
    from agent_desk.fakes import ScriptedModel
    from agent_desk.handled import Handled
    from agent_desk.mcp_client import McpTools
    from agent_desk.mcp_server import create_server
    from agent_desk.messages import BadMessage, parse_message
    from agent_desk.model import Model
    from agent_desk.resolver import Resolver
    from agent_desk.simulator import load_tickets, simulate
    from agent_desk.triage import Triage

    settings = load_settings()
    if bus is None:
        bus = MemoryBus()
        simulate(bus, count=args.count, seed=args.seed, path=args.data)
        print("MemoryBus demo: all messages stay in this process.")
    store = Handled(args.handled_path)
    resolver = None

    def unseen(topic, consumer, stage):
        """Build fake replies only for new, unique valid tickets."""
        seen = set()
        messages = []
        for record in read_topic(bus, topic):
            try:
                message = parse_message(record.value)
            except BadMessage:
                continue
            if message.ticket_id in seen or store.connection.execute(
                "SELECT 1 FROM handled WHERE consumer=? AND idempotency_key=?",
                (consumer, f"{message.ticket_id}:{stage}"),
            ).fetchone():
                continue
            seen.add(message.ticket_id)
            messages.append(message)
        return messages

    def drain(topics, group, runner):
        """Close a subscription after its available records are handled."""
        subscription = bus.consume(topics, group)
        try:
            return runner.run(subscription)
        finally:
            subscription.close()

    retry = {"max_attempts": settings.max_attempts, "backoff_base_s": settings.backoff_base_s}
    counts = {}
    try:
        if args.agent in {"all", "triage"}:
            model = Model(settings)
            if args.fake:
                labels = {item.ticket_id: item for item in load_tickets(args.data)}
                script = []
                for message in unseen("desk.tickets", "triage", "triage"):
                    label = labels.get(message.ticket_id)
                    script.append({"text": json.dumps({
                        "category": label.category if label else "other",
                        "priority": label.priority if label else "normal",
                    })})
                model = ScriptedModel(script)
            counts["triage"] = drain(["desk.tickets"], "triage", Triage(bus, model).runner(store, **retry))
        if args.agent in {"all", "resolver"}:
            model = ScriptedModel([]) if args.fake else Model(settings)
            if args.fake:
                seed(settings.db_path)
            tools = McpTools(create_server(settings.db_path)) if args.fake else McpTools(db_path=settings.db_path)
            resolver = Resolver(bus, model, tools, settings)
            if args.fake:
                script = []
                for message in unseen("desk.work", "resolver", "resolve"):
                    saved = resolver.graph.get_state({"configurable": {"thread_id": message.ticket_id}})
                    if saved.values and (not saved.next or saved.interrupts):
                        continue
                    refund = message.payload.category == "refund"
                    if not saved.values or "plan" in saved.next:
                        script.append({"text": json.dumps({"action": "refund" if refund else "status"})})
                    script.append({"text": json.dumps({"action": "refund", "amount": 1} if refund else
                                                     {"action": "reply", "reply": "Shop facts checked."})})
                model.script.extend(script)
            counts["resolver"] = drain(["desk.work"], "resolver", resolver.runner(store, **retry))
            counts["decisions"] = drain(["desk.approvals.decisions"], "resolver-decisions",
                                        resolver.decision_runner(store, **retry))
    finally:
        if resolver is not None:
            resolver.close()
        store.close()
    print("Handled " + ", ".join(f"{name}={count}" for name, count in counts.items()))
    _results(bus)


def _results(bus):
    """Show one row per ticket, including repeated result publishes only once."""
    from agent_desk.approver import read_topic
    from agent_desk.messages import TicketResolvedEnvelope, parse_message

    print("TICKET | STATUS | REFUND | REPLY")
    seen = set()
    for record in read_topic(bus, "desk.results"):
        message = parse_message(record.value)
        if not isinstance(message, TicketResolvedEnvelope) or message.ticket_id in seen:
            continue
        seen.add(message.ticket_id)
        result = message.payload
        amount = "-" if result.refund_amount is None else f"{result.refund_amount:.2f}"
        print(f"{message.ticket_id} | {result.status} | {amount} | {result.reply}")


def main(argv: list[str] | None = None, *, bus: Bus | None = None) -> int:
    """Run local desk commands, with an injectable bus for offline sessions."""
    parser = argparse.ArgumentParser(prog="agent-desk")
    commands = parser.add_subparsers(dest="command")
    simulator = commands.add_parser("simulate")
    simulator.add_argument("--count", type=int, default=40)
    simulator.add_argument("--seed", type=int, default=0)
    simulator.add_argument("--poison", type=int, default=0)
    simulator.add_argument("--duplicate", type=int, default=0)
    simulator.add_argument("--data", default="data/tickets.jsonl")
    run = commands.add_parser("run")
    run.add_argument("agent", nargs="?", choices=("all", "triage", "resolver"), default="all")
    run.add_argument("--fake", action="store_true")
    run.add_argument("--count", type=int, default=40)
    run.add_argument("--seed", type=int, default=0)
    run.add_argument("--data", default="data/tickets.jsonl")
    run.add_argument("--handled-path", default=".agent-desk/handled.sqlite")
    evaluation = commands.add_parser("eval").add_subparsers(dest="eval_kind", required=True).add_parser("triage")
    evaluation.add_argument("--fake", action="store_true")
    evaluation.add_argument("--script")
    evaluation.add_argument("--data", default="data/tickets.jsonl")
    evaluation.add_argument("--output-dir", default="runs")
    commands.add_parser("results")
    approve = commands.add_parser("approve")
    approve.add_argument("ticket_id", nargs="?")
    choices = approve.add_mutually_exclusive_group()
    choices.add_argument("--accept", action="store_true")
    choices.add_argument("--reject", action="store_true")
    approve.add_argument("--reviewer", default="")
    approve.add_argument("--note", default="")
    approve.add_argument("--web", action="store_true")
    approve.add_argument("--port", type=int, default=8765)
    seed_parser = commands.add_parser("seed")
    seed_parser.add_argument("--db-path")
    dlq = commands.add_parser("dlq").add_subparsers(dest="action", required=True)
    dlq.add_parser("list")
    replay_parser = dlq.add_parser("replay")
    replay_parser.add_argument("offset", type=int)
    args = parser.parse_args(argv)
    if args.command == "run":
        _run(bus, args)
        return 0
    if args.command == "results":
        _results(bus if bus is not None else MemoryBus())
        return 0
    if args.command == "simulate":
        from agent_desk.simulator import simulate

        count = simulate(bus if bus is not None else MemoryBus(), count=args.count, seed=args.seed,
                         poison=args.poison, duplicate=args.duplicate, path=args.data)
        print(f"Published {count} messages to desk.tickets (MemoryBus is process-local).")
        return 0
    if args.command == "eval":
        from agent_desk.evals import copying_model, evaluate_triage
        from agent_desk.fakes import ScriptedModel
        from agent_desk.model import Model
        from agent_desk.simulator import load_tickets

        if args.script and not args.fake:
            parser.error("--script requires --fake")
        tickets = load_tickets(args.data)
        model = (ScriptedModel(args.script) if args.script else copying_model(tickets)) if args.fake else Model()
        result = evaluate_triage(model, tickets, model_name="scripted" if args.fake else load_settings().model,
                                 output_dir=args.output_dir)
        print(f"Category accuracy: {result['category_accuracy']:.4f}")
        print(f"Priority accuracy: {result['priority_accuracy']:.4f}")
        print("FIELD | EXPECTED | PREDICTED | COUNT")
        for field, rows in result["confusion"].items():
            for expected, cells in rows.items():
                for predicted, count in cells.items():
                    print(f"{field} | {expected} | {predicted} | {count}")
        return 0
    if args.command == "approve":
        from agent_desk.approver import create_web_server, decide, pending

        bus = bus if bus is not None else MemoryBus()
        if args.web:
            with create_web_server(bus, args.port) as server:
                print(f"Approver at http://127.0.0.1:{server.server_port}")
                server.serve_forever()
        elif args.ticket_id:
            if not (args.accept or args.reject):
                parser.error("Choose --accept or --reject")
            try:
                decide(bus, args.ticket_id, args.accept, args.reviewer, args.note)
            except ValueError as error:
                parser.error(str(error))
            print(f"Decision sent for {args.ticket_id}")
        else:
            for request in pending(bus):
                print(request.ticket_id, f"{request.payload.amount:.2f}", request.payload.reason)
        return 0
    if args.command == "seed":
        path = args.db_path if args.db_path is not None else load_settings().db_path
        seed(path)
        print(f"Seeded {path}")
        return 0
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
