# foundry_telegram_invocations_weather

Telegram weather bot sample for validating a non-Responses channel on Foundry
Hosted Agents. The sample configures `TelegramChannel(path="/invocations")` so
the webhook handler runs at the container endpoint `POST /invocations`; Foundry
exposes that route publicly as:

```text
{FOUNDRY_PROJECT_ENDPOINT}/agents/agent-framework-telegram-invocations-weather/endpoint/protocols/invocations?api-version=2025-11-15-preview
```

| Route | Channel | Used by |
|---|---|---|
| `POST /responses` | `ResponsesChannel` | Quick hosted-agent sanity checks |
| `POST /invocations` | `TelegramChannel` | Telegram webhook payloads |

The agent uses `FoundryHostedAgentHistoryProvider` and a small
`lookup_weather` tool so Telegram requests exercise model calls, tool calls,
and Foundry-hosted storage.

## Important platform note

This is an intentional experiment. Current Foundry Hosted Agents behavior
requires Entra bearer auth before a request reaches the container. Telegram
cannot attach that bearer token to webhook deliveries, so webhook registration
can succeed while live Telegram deliveries fail at the Foundry front door with
`401`. Authenticated calls to the Invocations endpoint are still useful for
validating the channel and storage behavior inside the container.

The sample does not configure `TELEGRAM_WEBHOOK_SECRET` because prior probing
showed Foundry strips Telegram's `X-Telegram-Bot-Api-Secret-Token` header before
the request reaches the container.

## Run locally

```bash
export FOUNDRY_PROJECT_ENDPOINT=https://<your-project>.services.ai.azure.com
export MODEL_DEPLOYMENT_NAME=gpt-5.4-nano
export TELEGRAM_BOT_TOKEN=<telegram-bot-token>
export TELEGRAM_WEBHOOK_URL=https://<public-local-tunnel>/invocations
az login

uv sync
uv run python app.py
```

## Deploy

```bash
set -a
. ../../../../.env
set +a

azd env set TELEGRAM_BOT_TOKEN "$TELEGRAM_BOT_TOKEN"
azd env set MODEL_DEPLOYMENT_NAME "${MODEL_DEPLOYMENT_NAME:-gpt-5.4-nano}"
azd env set HOSTING_INVOCATIONS_API_VERSION 2025-11-15-preview
azd up
```

If you connect this sample to an existing Foundry project instead of running
`azd provision`, make sure the azd environment has `AZURE_AI_PROJECT_ID` and the
project's ACR connection values set before running `azd deploy`.

On startup, `TelegramChannel` calls `setWebhook` using the Foundry public
Invocations URL derived from `FOUNDRY_PROJECT_ENDPOINT` and
`FOUNDRY_AGENT_NAME`.
