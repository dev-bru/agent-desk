# 02: Consumer groups

Concept: consumers in one group share work; different groups each get their own
view of a topic. This lets two triage workers share tickets while an audit reader
sees every ticket.

Run from the project folder:

```powershell
.venv/Scripts/python.exe -B lessons/02-consumer-groups.py --fake
```

Expected output on stdout:

```text
triage workers: T-1 and T-2; uncommitted T-1 redelivered
independent audit group: T-1, T-2
```

Follow the logic step by step:

1. Publish two records with different keys. Two consumers join group `triage`.
   Each claims a different record, so both can work at the same time.
2. The second worker commits `T-2`. The first worker closes without committing
   `T-1`, which makes that record available to the remaining worker.
3. After `T-1` is acknowledged, the triage group has no work. `read_topic()` uses
   a fresh group and reads both records, including the committed ones. A commit
   belongs to a group, not to every reader of the topic.

Files to read: `src/agent_desk/bus.py:77` (claim records and block pending keys),
`src/agent_desk/bus.py:101` (commit), `src/agent_desk/bus.py:110` (close),
`src/agent_desk/approver.py:14` (fresh reader group), and
`tests/test_memory_bus.py:23` (group sharing).
Continue with [the deeper bus lesson](../docs/learn/lessons/deep-01-event-bus.md).

This script uses `MemoryBus` in one process today. It models group sharing and
redelivery, without modeling Kafka partitions or rebalances. Native Kafka and
broker-based group exercises are coming with F-010. No partition setting is
needed for this working path.

Quiz: Which group gets a record again after an uncommitted close? Why can the audit
reader still read committed records? Why do these two tickets use different keys?
