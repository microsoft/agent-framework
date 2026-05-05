# local_telegram — `@tool`, file-backed history, hooks, multicast

Builds on `foundry_hosted_agent/` with the hooks and config most real apps need:

- A `@tool`-decorated function call (`get_weather`) so streaming and tool
  invocation are exercised end-to-end.
- `FileHistoryProvider(./storage/sessions)` so per-user/per-chat history
  survives restarts.
- A `responses_hook` that keys each session off the OpenAI
  `safety_identifier` field, so multiple users on the Responses endpoint
  do not share history.
- A `telegram_hook` that keys per-chat sessions via `telegram_isolation_key`.
- Two extra Telegram commands (`/new`, `/whoami`).
- `ResponseTarget` multicast: a Responses request can fan out the agent
  reply to a Telegram chat by passing
  `extra_body={"response_target": ["originating", "telegram:<chat_id>"]}`.

`app:app` is a module-level Starlette ASGI app, so this sample runs under
Hypercorn (multi-process).

## Run

```bash
export FOUNDRY_PROJECT_ENDPOINT=https://<your-project>.services.ai.azure.com
export FOUNDRY_MODEL=gpt-4o
export TELEGRAM_BOT_TOKEN=...
az login

uv sync
uv run hypercorn app:app \
    --bind 0.0.0.0:8000 \
    --workers 4
```

Single-process for quick iteration:

```bash
uv run python app.py
```

## Call locally

```bash
uv sync --group dev

# Plain call:
uv run python call_server.py "What is the weather in Tokyo?"

# Resume an existing session by AgentSession id (works across channels):
uv run python call_server.py --previous-response-id telegram:8741188429 "What did we discuss?"

# Multicast: keep the reply on the local wire AND push it to Telegram.
uv run python call_server_multicast.py --telegram-chat-id 8741188429 "Heads up."
```

> This sample is **local-only** — it shows the `agent-framework-hosting`
> server stack as a standalone process. For a Foundry-Hosted-Agents-compatible
> packaging (Dockerfile + `agent.yaml` + `azure.yaml`), see
> [`foundry_hosted_agent/`](../foundry_hosted_agent).
