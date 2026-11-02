# 03: An agent is a consumer

Concept: an agent reads a message, asks a model for a decision, checks that answer,
and publishes the next event. A shared runner handles retries and repeated work.
This keeps delivery rules out of the model prompt.

Run from the project folder:

```powershell
.venv/Scripts/python.exe -B lessons/03-agent-as-consumer.py --fake
```

Expected output on stdout (JSON logs and trace spans also go to stderr):

```text
desk.work: T-1 order_status normal
2 deliveries; 1 model call; 1 work event
```

Follow the logic step by step:

1. Create a labeled example and use `ticket_message()` to strip its answer labels
   from the wire payload. Publish the same ticket twice to model a repeat.
2. `ScriptedModel` supplies one fixed JSON answer. It has the real model's `chat()`
   interface, so the actual triage code runs without a model server or provider key.
3. The runner checks the envelope and uses `T-1:triage` as the handled key.
   `Triage.handle()` checks the model's category and priority before publishing
   to `desk.work`. Invalid output gets one repair prompt, then an error.
4. The handled key makes the second delivery skip the model and the publish.
   The script checks one output event and one model request. This in-memory store
   lasts for the script; the desk uses a file to keep keys across restarts.

Files to read: `src/agent_desk/simulator.py:29` (strip labels),
`src/agent_desk/triage.py:33` (handle), `src/agent_desk/triage.py:65` (runner),
`src/agent_desk/handled.py:21` (transaction), and `src/agent_desk/fakes.py:43`
(`chat`). Read [deep lesson 5](../docs/learn/lessons/deep-05-triage-structured-output.md)
for the schema and repair details.

`MemoryBus` carries tickets and work in this single process today. Kafka consumers
in separate processes are coming with F-010. The model stays scripted on this
path, so no model server, broker, network, or API key is required.

Quiz: Why strip labels before publishing? What prevents a repeat from calling the
model twice? What can happen if the process stops after publishing but before
saving the handled key?
