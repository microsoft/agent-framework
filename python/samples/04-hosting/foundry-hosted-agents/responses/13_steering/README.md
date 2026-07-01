# What this sample demonstrates

How to enable **steerable conversations** with `ResponsesHostServer`.

When `steerable_conversations=True`, a client can send a new turn to the same
conversation while the previous turn is still running.  Instead of receiving
HTTP 409 `conversation_locked`, the new turn is queued and the running handler
receives a cooperative cancellation signal.  Once the current turn terminates,
the queued turn runs.

## How It Works

1. The server starts with `steerable_conversations=True`.
2. Turn 1 is sent as a foreground streaming request on a shared conversation.
3. Two seconds later, while turn 1 is still streaming, turn 2 arrives on the
   same conversation.  The server immediately returns `status=queued`.
4. The running handler observes `cancellation_signal.is_set()` (with
   `context.client_cancelled=False`, distinguishing steering from a real cancel)
   and emits `response.completed` with partial output.
5. Once turn 1 finishes the framework drains the queue and invokes the handler
   again for turn 2 (with `context.is_steered_turn=True`).

See [main.py](main.py) for the server and [client.py](client.py) for the
interactive demo.

## Running the Sample

**Terminal 1 — start the server:**

```bash
uv run python main.py
```

**Terminal 2 — run the demo client:**

```bash
uv run python client.py
```

You will see turn 1 streaming, turn 2 arriving as `status=queued`, turn 1
cutting off, and then turn 2's answer appearing.  The server terminal shows
the steering signal and handler cancellation in real time.

You can also point the client at a deployed instance:

```bash
uv run python client.py https://your-deployed-agent-url
```

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
