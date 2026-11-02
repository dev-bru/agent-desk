# 01: Event basics

Concept: an event records something that happened. A topic is an ordered log of
events. A producer can leave work for a consumer without calling that consumer.
This lets the two parts run at different times.

Run from the project folder with the supplied environment:

```powershell
.venv/Scripts/python.exe -B lessons/01-event-basics.py --fake
```

Expected output on stdout:

```text
Read ticket.created for T-1 at offset 0
Committed; no pending event
```

Follow the logic step by step:

1. The script makes a `MemoryBus` and publishes JSON to `desk.tickets`. The key
   `T-1` ties the record to one ticket; offset 0 is its position in this topic.
2. `poll()` claims a record for the reader group. `parse_message()` checks its
   envelope and payload before the consumer uses them. Bytes alone are not proof
   that the producer sent a valid ticket.
3. `commit()` acknowledges the record for this group. The next poll has no work.
   The topic still holds the event; a new group can read it.

Files to read: `src/agent_desk/bus.py:47` (`MemoryBus`),
`src/agent_desk/bus.py:77` (`poll`), `src/agent_desk/messages.py:113`
(`parse_message`), and `lessons/01-event-basics.py:9` (the complete example).
For the longer explanation, read [deep lesson 1](../docs/learn/lessons/deep-01-event-bus.md).

The working path today is `MemoryBus` in one process. Kafka persistence, the native
Windows broker, and `KafkaBus` are coming with F-010. Separate terminals do not
share this memory log. No broker or model is needed here.

Quiz: Why does the consumer validate JSON? Does committing remove the event from
the topic? Which value identifies the ticket, and which identifies its position?
