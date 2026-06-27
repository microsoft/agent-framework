# local_multi_channel — Responses + Telegram, shared history, cross-channel sessions

Runs the same agent behind two channels at once: an OpenAI-compatible
**Responses** HTTP endpoint and a **Telegram** bot. Both channels share a
`FileHistoryProvider`, so history is preserved per user/chat across restarts
and the same conversation can be resumed from either surface.

What this sample shows:

- A `@tool`-decorated function (`lookup_weather`) exercised end-to-end.
- `FileHistoryProvider(./storage/sessions)` — per-user/per-chat history that
  survives restarts.
- `responses_hook` — strips caller-supplied `model`/`store`/`temperature`, keys
  each Responses session off the `safety_identifier` field, and supports
  resuming a Telegram chat by passing its isolation key as
  `previous_response_id`.
- `telegram_hook` — strips `model` and raises reasoning effort for a richer
  Telegram persona.
- `/new`, `/whoami`, `/weather <city>` Telegram commands.

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

## Call via the Responses endpoint

```bash
uv sync --group dev

# Plain call:
uv run python call_server.py "What is the weather in Tokyo?"

# Resume a Telegram chat session from the Responses endpoint:
uv run python call_server.py --previous-response-id telegram:8741188429 "What did we discuss?"
```

> This sample is **local-only** — it shows the `agent-framework-hosting`
> server stack as a standalone process. For Foundry-hosted deployment
> guidance see [`../../../../packages/foundry_hosting/README.md`](../../../../packages/foundry_hosting/README.md).
