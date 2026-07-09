# What this sample demonstrates

How to enable **crash recovery** (`resilient_background=True`) with
`ResponsesHostServer`.

When `resilient_background=True`, if the server process crashes or is
restarted while handling a background request, the Foundry platform
automatically re-invokes the handler on the next process start.  The client
does not need to retry — the response picks up where it left off.  Persisted
SSE events are also replayed to clients that reconnect with `starting_after=`.

## How It Works

1. The server starts with `resilient_background=True` via `ResponsesServerOptions`.
2. A client sends a background streaming request (`background=true`, `store=true`).
3. The server immediately returns `status=in_progress` and the handler runs
   inside a resilient task.
4. If the server crashes before the handler completes, the agentserver recovery
   scanner fires on the next startup and re-invokes the handler.
5. The response transitions from `in_progress` back to running and eventually
   reaches `completed`.

See [main.py](main.py) for the server implementation and [demo.py](demo.py) for
the automated crash-recovery demonstration.

## Demonstrating Crash Recovery

`demo.py` orchestrates the full recovery cycle automatically — no manual
timing needed:

```bash
uv run python demo.py
```

It will:

1. Start the server (`main.py`) as a background process
2. Send a background request and note the response ID (`status=in_progress`)
3. Kill the server after 2 seconds (simulates a crash)
4. Restart the server (the recovery scanner runs on startup)
5. Poll the response and print it once it reaches `completed`

Expected output:
```
Step 1/5  Starting server...
          Server ready (pid=12345)

Step 2/5  Sending background request...
          Response ID : caresp_...
          Status      : in_progress  (handler is running)

Step 3/5  Simulating crash (terminating server)...
          Server killed (exit code: -15)

Step 4/5  Restarting server (recovery scanner will fire)...
          Server restarted (pid=12346)

Step 5/5  Polling response (watching recovery)...
          status: in_progress
          status: in_progress
          status: completed

Recovered response (34228 chars):
Below is a compact evidence pack you can use for a 24-hour training-energy / CO2e ...
```

## Environment Variables

Copy `.env.example` to `.env` and fill in your values:

```
FOUNDRY_PROJECT_ENDPOINT=https://...
AZURE_AI_MODEL_DEPLOYMENT_NAME=gpt-4o
```

Run `az login` before running the demo.

## Deploying the Agent to Foundry

To host the agent on Foundry, follow the instructions in the
[Deploying the Agent to Foundry](../../README.md#deploying-the-agent-to-foundry)
section of the README in the parent directory.  On Foundry, container rotations
exercise the same recovery path automatically.

