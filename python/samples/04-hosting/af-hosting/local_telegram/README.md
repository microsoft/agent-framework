# local_telegram — Telegram bot with `@tool`, file-backed history, slash commands

Minimal sample for hosting an agent as a Telegram bot using
`agent-framework-hosting` + `agent-framework-hosting-telegram`.

What this sample shows:

- A `@tool`-decorated function (`lookup_weather`) exercised end-to-end with streaming.
- `FileHistoryProvider(./storage/sessions)` — per-chat history that survives restarts.
- `run_hook` — strips caller-supplied `model` and raises reasoning effort.
- Slash commands: `/start`, `/help`, `/new`, `/whoami`, `/weather <city>`.

`app:app` is a module-level Starlette ASGI app.

## Run

```bash
export FOUNDRY_PROJECT_ENDPOINT=https://<your-project>.services.ai.azure.com
export FOUNDRY_MODEL=gpt-4o
export TELEGRAM_BOT_TOKEN=...
az login

uv sync
uv run python app.py
```

Production launch with Hypercorn (polling transport — no public URL needed):

```bash
uv run hypercorn app:app --bind 0.0.0.0:8000 --workers 4
```

Webhook transport (requires a public HTTPS URL, e.g. via `ngrok`):

```bash
export TELEGRAM_WEBHOOK_URL=https://<your-host>/telegram/webhook
uv run hypercorn app:app --bind 0.0.0.0:8000
```

> This sample is **local-only**. For a multi-channel variant that also exposes
> an OpenAI-compatible Responses endpoint, see
> [`../local_multi_channel/`](../local_multi_channel).
