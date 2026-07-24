# agent-framework-hosting-telegram

Telegram Bot API-shaped helpers for app-owned Agent Framework hosting.

This is an alpha, helper-only package: it converts between Telegram's
`Update` JSON shape and Agent Framework run values in both directions. It
does **not** provide a bot client, a hosting/channel registry, or a
long-running service. Your app remains fully responsible for:

- **Fetching updates** -- long polling (`getUpdates`) or registering a
  webhook -- and for verifying webhook authenticity (e.g. Telegram's secret
  token header, or an IP allowlist).
- **The Bot API client** -- issuing the actual HTTP calls (`sendMessage`,
  `sendPhoto`, `editMessageText`, `answerCallbackQuery`, `getFile`, ...) with
  whatever HTTP library you prefer.
- **Rate limits and retries** -- Telegram enforces per-chat and global rate
  limits; back off and retry on `429`/`5xx` yourself.
- **Command dispatch** -- `telegram_command(...)` only parses and normalizes
  a leading `/command`; your app decides what each command does.
- **Sessions/storage** -- pair these helpers with
  [`agent-framework-hosting`](https://pypi.org/project/agent-framework-hosting/)'s
  `AgentState` and core's `SessionStore` or `FileSessionStore` to persist
  `AgentSession`s across turns.

## Helpers

- `telegram_chat_id(update)` -- the chat id an update belongs to.
- `telegram_session_id(update, bot_id=...)` -- a bot-scoped `AgentState`
  session id. Private chats use `telegram_<bot_id>_user_<user_id>`; other chats
  use `telegram_<bot_id>_chat_<chat_id>`.
- `telegram_command(update)` -- a leading slash command, with `/name@bot args`
  normalized to `/name args`. Returns `None` if there is none.
- `telegram_callback_query_id(update)` -- a callback query's id, so you can
  call `answerCallbackQuery` yourself.
- `telegram_media_file_id(update_or_message)` -- the `(file_id, mime_type)`
  of inbound media (largest photo size, document, voice, audio, or video).
- `telegram_to_run(update, *, resolve_file_url=None, stream=False)` -- convert
  a `message`, `edited_message`, or `callback_query` update into
  `Agent.run` arguments. Provide `resolve_file_url` (typically backed by
  `getFile`) to turn inbound media into content; without it (or when it
  returns `None`), text/caption is preserved and media is otherwise dropped.
  Media-only input with no resolvable URL raises `ValueError`.
- `telegram_from_run(result, *, chat_id, parse_mode=None)` -- render a
  finished run as one `TelegramOperation` (`sendPhoto` when the response has
  an image, otherwise `sendMessage`, falling back to `"(no response)"`).
- `telegram_from_streaming_run(stream, *, chat_id, message_id,
  initial_text=None, parse_mode=None)` -- render a streaming run as
  `editMessageText` operations with the cumulative text so far, followed by any
  images in the final response as `sendPhoto` operations. Pass the
  app-created placeholder text as `initial_text` so an identical first edit is
  omitted. Image-only responses first emit `deleteMessage` for the placeholder.

`TelegramOperation` is a minimal `TypedDict` of `{"method": str, "payload": dict}`
-- your app is responsible for actually calling the Bot API with it.

```python
from agent_framework_hosting import AgentState
from agent_framework_hosting_telegram import (
    telegram_chat_id,
    telegram_from_run,
    telegram_session_id,
    telegram_to_run,
)

state = AgentState(agent)


async def handle_update(update: dict) -> None:
    chat_id = telegram_chat_id(update)
    if chat_id is None:
        return  # Not a chat update this bot handles.

    session_id = telegram_session_id(update, bot_id=bot.id)
    session = await state.get_or_create_session(session_id)
    run = await telegram_to_run(update, resolve_file_url=resolve_telegram_file_url)
    result = await (await state.get_target()).run(run["messages"], session=session, options=run["options"])
    await state.set_session(session_id, session)  # type: ignore[arg-type]

    operation = telegram_from_run(result, chat_id=chat_id)
    await call_bot_api(operation["method"], operation["payload"])  # Your HTTP client.
```

The base execution-state helpers live in
[`agent-framework-hosting`](https://pypi.org/project/agent-framework-hosting/).
