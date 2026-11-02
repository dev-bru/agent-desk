# 04: Graph state and restart

Concept: a graph has named steps and saved state. A checkpoint saves progress so
the resolver can continue at the next step after a restart. This avoids repeating
completed model and shop calls.

Run from the project folder:

```powershell
.venv/Scripts/python.exe -B lessons/04-graph-state.py --fake
```

Expected output on stdout:

```text
Saved: plan -> gather; next: decide
Resumed: decide -> reply; status: resolved; total model calls: 2
```

Follow the logic step by step:

1. Read a triaged status ticket from `desk.work` on `MemoryBus`. Seed a temporary
   shop and call its real FastMCP tools in-process. The model replies are scripted.
2. The first resolver runs `plan`, then `gather`. Shop facts say the mug is in
   transit. `interrupt_after=["gather"]` stops at a node boundary, after saving
   the facts and next step to a SQLite checkpoint.
3. Close that resolver and build another with the same checkpoint file and ticket
   id. `Resolver.run()` finds saved values and passes `None` as graph input to
   continue. Replacing the input with a new ticket would be a different operation.
4. The rebuilt graph starts at `decide`, then reaches `reply`. It consumes one new
   scripted answer, for two model calls across the saved run. It retains one
   `gather` step. `tests/test_resolver.py:87` also counts MCP calls to prove no
   repeated reads. `run()` returns state; the normal handler publishes the result.

Files to read: `src/agent_desk/resolver.py:24` (state),
`src/agent_desk/resolver.py:57` (graph builder), `src/agent_desk/resolver.py:190`
(checkpoint setup), and `src/agent_desk/resolver.py:202` (start or resume).
Read [deep lesson 6](../docs/learn/lessons/deep-06-langgraph-checkpoint-resume.md)
and [deep lesson 4](../docs/learn/lessons/deep-04-mcp-fastmcp.md) for more detail.

The script creates and removes its own `.pytest-tmp-lesson04-*` folder under the
project. It does not reset desk state. This controlled stop demonstrates a saved
node boundary; an interrupted node can still run again and needs safe effects.
MemoryBus messages do not survive a process exit, even though SQLite checkpoints
do. Native Kafka delivery across processes is coming with F-010.

Quiz: Why must the rebuilt graph use the same ticket id and checkpoint file? How
does a checkpoint differ from a handled key? What changes if a node stops before
its checkpoint is saved?
