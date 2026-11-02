# Follow a ticket with logs and traces

A ticket crosses several topics. A trace id joins these separate steps into one
story. `src/agent_desk/telemetry.py:50` reads W3C context and starts a child span.
The outgoing header helper carries the new span context to the next topic.
The runner wraps each delivery, including retries, in a span. The approver reads
the request's headers, so a human delay or resolver restart does not break the trace.

Logs are JSON objects with ids, an attempt count and a fixed event name. We omit
ticket bodies and provider exception text. The logger removes configured key
values before JSON escaping. This also handles keys with quotes or newlines.
Spans export locally to the console. No OTLP client or network exporter is created.

```powershell
.venv\Scripts\python.exe -m pytest tests/test_logging.py tests/test_tracing.py --basetemp=.pytest-tmp-observability
```

Expected output: `3 passed`. The trace test records spans in memory and checks one
trace through simulate, triage, resolve, approve and resumed resolve.

Quiz: Why must trace context travel in headers instead of a Python global? Which
two span attributes identify the ticket and topic? Why omit exception text from logs?
