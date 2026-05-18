# local_identity_link — every channel, plus identity linking

The full surface: Responses + Invocations + Telegram + Activity Protocol (Teams) + the Entra
identity-link sidecar. The Entra channel exposes
`/auth/start` + `/auth/callback` so users on Telegram (or any non-Entra
channel) can bind their per-channel id to a stable `entra:<oid>` isolation
key. Channel run-hooks then rewrite incoming requests to use the linked
key, so a chat started on Telegram and a chat started on Teams that both
resolve to the same Entra user share one history.

## Run

```bash
export FOUNDRY_PROJECT_ENDPOINT=https://<your-project>.services.ai.azure.com
export FOUNDRY_MODEL=gpt-4o
export TELEGRAM_BOT_TOKEN=...
# Entra app registration (confidential client):
export ENTRA_TENANT_ID=...
export ENTRA_CLIENT_ID=...
export ENTRA_CLIENT_SECRET=...                 # or:
# export ENTRA_CERTIFICATE_PATH=./teams-bot.pem
export PUBLIC_BASE_URL=https://<public-host>   # used to mint redirect_uri
# Teams (optional — same tenant):
export TEAMS_APP_ID=...
export TEAMS_APP_PASSWORD=...

az login

uv sync
uv run hypercorn app:app \
    --bind 0.0.0.0:8000 \
    --workers 4
```

## Identity link

Register `https://<public-host>/auth/callback` as the redirect URI on your
Entra app, then visit (replace ``<chat_id>`` with the Telegram numeric
chat id):

```
https://<public-host>/auth/start?channel=telegram&id=<chat_id>
```

After sign-in, subsequent Telegram messages from that chat resolve to the
linked Entra user.

## Call locally

```bash
uv sync --group dev

# Default: post a Responses request as `local-dev`.
uv run python call_server.py "What is the weather in Tokyo?"

# Resume any session by id, including a Telegram one (works because
# the Telegram run-hook writes sessions under telegram:<chat_id>):
uv run python call_server.py --previous-response-id telegram:8741188429 "What did we discuss?"

# Multicast to a Telegram chat in parallel with the local response:
uv run python call_server.py --telegram-chat-id 8741188429 "Heads up."
```

> This sample is **local-only** — it shows the `agent-framework-hosting`
> server stack as a standalone process. For a Foundry-Hosted-Agents-compatible
> packaging (Dockerfile + `agent.yaml` + `azure.yaml`), see
> [`foundry_hosted_agent/`](../foundry_hosted_agent).
