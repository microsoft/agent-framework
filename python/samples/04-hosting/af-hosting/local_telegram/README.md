# local_telegram - Telegram helpers with aiogram polling or webhooks

A local Telegram bot built from the helper-first hosting pieces:

- an actual Foundry-backed Agent Framework `Agent`;
- `AgentState` and `InMemoryHistoryProvider` for process-local per-chat
  continuity;
- `telegram_to_run(...)` for Telegram update to AF conversion;
- `telegram_from_streaming_run(...)` for AF stream to Telegram edit payloads;
- `aiogram` for typed updates, polling/webhook dispatch, file download, and Bot
  API calls.

There is no Telegram client, polling runtime, webhook router, command registry,
or delivery framework in `agent-framework-hosting-telegram`. This sample uses
the native `aiogram` SDK for those concerns. The helpers are deliberately
agnostic to the Telegram SDK you choose. See the
[Telegram documentation](https://core.telegram.org/bots/samples#python) for
other Python SDK options.

Each entry point is intentionally self-contained so it can be read and copied
without following a shared sample helper module. Both handle text, captions,
supported media, callback-query data, and the commands `/start`, `/help`,
`/new`, and `/weather <city>`.

## Run with polling

Create a Telegram bot with BotFather, then configure:

```bash
export FOUNDRY_PROJECT_ENDPOINT=https://<your-project>.services.ai.azure.com
export FOUNDRY_MODEL=gpt-5-nano
export TELEGRAM_BOT_TOKEN=...
az login

uv run polling_app.py
```

The sample asks `aiogram` to clear any existing webhook before polling because
Telegram does not allow polling while a webhook is registered.

## Run with a webhook

Configure the public HTTPS URL that Telegram should call and a random secret
used to authenticate webhook deliveries:

```bash
export FOUNDRY_PROJECT_ENDPOINT=https://<your-project>.services.ai.azure.com
export FOUNDRY_MODEL=gpt-5-nano
export TELEGRAM_BOT_TOKEN=...
export TELEGRAM_WEBHOOK_URL=https://<your-host>/telegram/webhook
export TELEGRAM_WEBHOOK_SECRET=<random-secret>
az login

uv run app.py
```

Each entry point declares its complete Agent Framework and third-party
dependency set using PEP 723 inline script metadata, so `uv` creates the
appropriate environment directly from the selected script.

`app.py` derives its FastAPI route from the path in
`TELEGRAM_WEBHOOK_URL`, registers that URL with Telegram during application
startup, and validates `X-Telegram-Bot-Api-Secret-Token` with
`TELEGRAM_WEBHOOK_SECRET` before accepting an update.

The app intentionally leaves the webhook registered during shutdown. Deleting
it can race a rolling deployment and remove the webhook that the replacement
process just registered.

## Behavior to notice

- **Session continuity:** `telegram_session_id(..., bot_id=bot.id)` follows
  Telegram's native identity boundaries. Private chats use
  `telegram_<bot_id>_user_<user_id>`; groups and supergroups use
  `telegram_<bot_id>_chat_<chat_id>`, creating a shared session for that group.
  Including `bot.id` prevents two bots from accidentally sharing state.
  aiogram derives that numeric bot id from `TELEGRAM_BOT_TOKEN`, so these local
  apps do not need a separate `TELEGRAM_BOT_ID` setting.
- **Starting over:** `/new` calls `state.session_store.delete(session_id)`.
  The command itself does not run the agent. On the next ordinary message,
  `get_or_create_session(...)` finds no stored value and creates a fresh
  `AgentSession` with empty `InMemoryHistoryProvider` state. In a group, this
  resets the shared group session; an app that wants per-user group sessions
  should include both the chat id and sender id in its app-owned key.
- **Process restarts:** history is intentionally process-local in this sample.
  Restarting either app also starts fresh. A durable deployment must replace
  both the in-memory session store and history provider deliberately.
- **Commands:** recognized commands are handled by application code and bypass
  the agent. Unknown slash commands fall through as ordinary agent input.
- **Callback queries:** the app acknowledges callback queries first to clear
  Telegram's loading indicator, then treats callback data as user input unless
  it matched an app-owned command.
- **Media:** files larger than 5 MiB are not forwarded. Downloaded media is
  converted to an inline data URI so a token-bearing Telegram file URL is not
  disclosed to the model provider. If media cannot be resolved, a caption can
  still be used as text; unresolved media-only updates are ignored.
- **Streaming:** the app sends a placeholder, applies cumulative text with
  `editMessageText`, and throttles edits. Telegram can normalize distinct
  payloads to the same rendered content; the app treats only its resulting
  `message is not modified` edit error as an idempotent success. Other Bot API
  errors still propagate. For an image-only result, the helper deletes the
  placeholder before emitting `sendPhoto`.
- **Transport ordering:** polling uses `tasks_concurrency_limit=1`, so this
  compact sample processes updates serially. The webhook acknowledges first
  and processes in a FastAPI background task, but serializes each chat's
  updates with an in-process lock so `/new` cannot race an in-flight response.
  A multi-process deployment must instead use its storage backend's locking or
  transaction mechanisms, or another cross-process ordering strategy.
- **Webhook trust:** `TELEGRAM_WEBHOOK_SECRET` authenticates delivery from
  Telegram. It does not authorize the Telegram user or chat to access
  application data.

## What the app owns

The helper package only converts protocol values. `aiogram`, `app.py`, and
`polling_app.py` own:

- polling or FastAPI webhook setup and update dispatch;
- bounded media download and inline-data conversion, avoiding disclosure of
  token-bearing Telegram file URLs to the model provider;
- slash-command policy and session reset;
- native send, photo, typing, callback acknowledgement, and edit calls;
- edit throttling and error logging.

That code remains visible so an application can replace it with a webhook,
queue, or retry policy without changing the AF conversion helpers.

## Production readiness

These are compact hosting samples, not complete production Telegram
deployments.
Before deploying this pattern:

- use HTTPS and keep webhook secret validation enabled;
- store `TELEGRAM_BOT_TOKEN` in a secret manager and avoid logging Bot API URLs;
- authorize users before mapping a chat id to sensitive/shared state;
- replace process-local history/session state with durable storage partitioned
  by tenant/user and define retention;
- make update processing idempotent and preserve per-chat ordering; use
  storage-backed locking/transactions or another distributed coordination
  mechanism when running more than one process;
- handle Telegram `429` responses and `retry_after` values;
- add bounded retries, delivery telemetry, and dead-letter handling;
- decide how partial streaming edits should recover when a final edit fails.

> This sample is **self-hosted**. The multi-protocol Telegram + Invocations
> Foundry-hosted sample remains part of the separate Invocations work.
