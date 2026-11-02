# Learn with known tickets before using a live model

The simulator and eval answer different questions. The simulator asks whether the
desk handles delivery, repeats and bad input. The eval asks whether triage chooses
the right labels. Neither needs Kafka or a model server in fake mode.

1. `data/tickets.jsonl:1` starts a set of 40 fictional tickets with expected category
   and priority. Orders and customer ids match the seeded shop.
2. `src/agent_desk/simulator.py:20` validates the complete set. The simulator uses a
   private seeded random generator, so another caller cannot change its order.
3. `src/agent_desk/simulator.py:29` removes the expected labels before building the
   wire message. The model must not see the answer in its input.
4. `src/agent_desk/simulator.py:38` publishes the selected tickets. Duplicate options
   resend the same envelope and message id. Poison options add messages that fail
   schema checks, so the runner sends them to the dead-letter topic.
5. `src/agent_desk/evals.py:22` runs the real triage handler. It counts each expected
   and predicted label pair, then divides correct answers by the set size. Category
   and priority scores are separate; `accuracy` counts tickets with both correct.
6. The report includes the model name, set size and confusion cells. A timestamp
   file name avoids overwriting earlier runs. CLI results collapse repeats by ticket.

```powershell
.venv\Scripts\python.exe -m agent_desk.cli eval triage --fake
.venv\Scripts\python.exe -m pytest tests/test_simulator.py tests/test_evals.py tests/test_cli.py --basetemp=.pytest-tmp-simulation
```

Expected output: category and priority accuracy `1.0000`, then a confusion table;
the tests end with `14 passed`. A report appears at `runs/eval-<time>.json`.
The copying fake is a test oracle: a perfect fake score checks the plumbing and
does not measure a real model's quality. Use `--fake --script <file>` to try wrong
answers; a script is a JSON list of objects such as `{"text":"...JSON labels..."}`.

Quiz: Why remove labels from the message? Why does one wrong category give 39/40
accuracy but leave priority accuracy at 1? Why keep a duplicate message id unchanged?
