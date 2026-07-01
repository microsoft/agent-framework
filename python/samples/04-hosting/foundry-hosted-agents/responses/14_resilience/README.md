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

See [main.py](main.py) for the server implementation.

## Testing Crash Recovery Locally

The agentserver uses a file-backed response store under `~/.agentserver/` by
default when not connected to Foundry, which satisfies the persistence
requirement for `resilient_background=True`.

**Step 1 — start the server:**

```bash
uv run python main.py
```

**Step 2 — send a long background request and note the response ID:**

```bash
curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input": "Count from 1 to 1000, one number per line.", "background": true, "store": true, "stream": true}'
```

Note the `id` field in the response JSON.

**Step 3 — kill the server mid-response:**

Press `Ctrl+C` in the server terminal while the agent is still counting.

**Step 4 — restart the server:**

```bash
uv run python main.py
```

The recovery scanner runs on startup and automatically re-invokes the handler.

**Step 5 — poll the response:**

```bash
curl http://localhost:8088/responses/REPLACE_WITH_RESPONSE_ID
```

You will see `status` transition through `in_progress` (recovering) and
eventually reach `completed`.

## Testing on Foundry

Deploy the agent and send a long background request.  The platform manages
container lifecycle; a container rotation mid-request exercises the same
recovery path automatically.

## Environment Variables

Copy `.env.example` to `.env` and fill in your values:

```
FOUNDRY_PROJECT_ENDPOINT=https://...
AZURE_AI_MODEL_DEPLOYMENT_NAME=gpt-4o
```

Run `az login` before starting the server.

## Deploying the Agent to Foundry

To host the agent on Foundry, follow the instructions in the
[Deploying the Agent to Foundry](../../README.md#deploying-the-agent-to-foundry)
section of the README in the parent directory.
