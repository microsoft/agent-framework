# agent-framework-hosting-telegram

Telegram channel for [agent-framework-hosting](../hosting). Supports both
**polling** (default — no public URL required, perfect for local dev) and
**webhook** transports, multi-content messages (text + media), command
registration, and end-to-end SSE-style streaming via Telegram message edits.

## Usage

```python
from agent_framework_hosting import AgentFrameworkHost
from agent_framework_hosting_telegram import TelegramChannel

host = AgentFrameworkHost(
    target=my_agent,
    channels=[TelegramChannel(bot_token="...")],
)
host.serve()
```

For production, configure `webhook_url="https://…"` and the channel will
register the webhook on startup and receive updates over HTTPS.

## Identity & sessions

Each Telegram chat is mapped to an opaque isolation key
(`telegram:<chat_id>`) so other channels can opt into the same per-chat
session by reusing the same key. The helper `telegram_isolation_key(chat_id)`
is exported for that purpose.
