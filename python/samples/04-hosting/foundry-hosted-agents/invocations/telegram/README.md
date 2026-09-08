# Telegram bot with a Foundry Hosted Agent

This sample deploys a Telegram bot whose webhook is handled by an Agent Framework agent running as a Microsoft
Foundry Hosted Agent:

```text
Telegram -> API Management -> Foundry Hosted Agent (Invocations 2.0)
         -> Agent Framework -> Telegram Bot API
                    |
                    +-> Cosmos DB conversation history
```

It is a complete learning deployment rather than a production reference architecture. The sibling
[`af-hosting/local_telegram`](../../../af-hosting/local_telegram/) sample is the better starting point for local
polling, an app-owned FastAPI webhook, and in-memory state. This sample focuses on Foundry direct-code deployment,
APIM ingress, managed identities, and durable history.

## What is deployed

The self-contained Bicep templates create:

- a resource group, Foundry account and project, and model deployment;
- a Log Analytics workspace and Application Insights connected to the Foundry project;
- Consumption-tier API Management with a system-assigned managed identity;
- a Key Vault containing the Telegram bot token and webhook secret;
- a serverless Cosmos DB account, database, and `/session_id`-partitioned container.

These resources can incur Azure and model-usage charges. Consumption APIM, serverless Cosmos DB, telemetry
ingestion, and model tokens are usage-billed; availability and pricing vary by region.

## Prerequisites

1. Bash, `curl`, `jq`, and `openssl`.
2. Azure CLI with Bicep and Azure Developer CLI (`azd`) with the `azure.ai.agents` extension.
3. Authenticated Azure CLI and azd sessions with permission to create subscription deployments, role assignments,
   and the resources above.
4. A Telegram bot created with BotFather and its token in the current shell:

   ```bash
   export TELEGRAM_BOT_TOKEN="<bot-token>"
   ```

Do not place the token in `.env`, `azure.yaml`, an azd environment, or source control. The deployment writes it
directly to Key Vault as a secure Bicep parameter.

## Deploy

From this directory, run:

```bash
./deploy.sh
```

The script:

1. validates prerequisites, configuration, and resource-group ownership;
2. builds and previews Bicep before provisioning;
3. creates or selects an isolated azd environment and sets non-secret deployment outputs;
4. validates metadata and performs a Python 3.13 direct-code deployment whose remote build installs
   `pyproject.toml` dependencies (the PEP 621 metadata used by uv includes an equivalent Poetry dependency table
   for Foundry's current Oryx builder);
5. grants the hosted-agent identity Key Vault secret-read and Cosmos DB data-contributor roles;
6. checks the hosted endpoint and APIM secret rejection; and
7. registers and verifies the Telegram webhook for `message`, `edited_message`, and `callback_query`.

The script does not print tokens or webhook secrets. It creates a mode-`0600` parameter file only for the duration
of Bicep deployment and removes it on exit.

### Configuration

All settings are optional except `TELEGRAM_BOT_TOKEN`.

| Variable | Default | Purpose |
|---|---|---|
| `NAME_PREFIX` | `telegramagent` | 3-16 lowercase alphanumeric resource-name prefix |
| `AZURE_SUBSCRIPTION_ID` | current Azure CLI subscription | Target subscription |
| `AZURE_LOCATION` | `eastus2` | Foundry, APIM, Key Vault, and monitoring region |
| `COSMOS_LOCATION` | `AZURE_LOCATION` | Cosmos DB region; change if serverless capacity is unavailable |
| `RESOURCE_GROUP_NAME` | `rg-$NAME_PREFIX` | Dedicated resource group name |
| `AZD_ENV_NAME` | `$NAME_PREFIX-telegram` | Isolated azd environment |
| `APIM_PUBLISHER_EMAIL` | Azure account name | Required APIM publisher email |
| `APIM_PUBLISHER_NAME` | `Agent Framework sample` | APIM publisher name |
| `MODEL_NAME` | `gpt-5.6-luna` | Model and deployment name |
| `MODEL_VERSION` | `2026-07-09` | Model version |
| `MODEL_FORMAT` | `OpenAI` | Model format |
| `MODEL_SKU_NAME` | `DataZoneStandard` | Model deployment SKU |
| `MODEL_CAPACITY` | `10` | Model deployment capacity |
| `ENABLE_SENSITIVE_DATA` | `true` | Include prompts, responses, and tool data in exported telemetry |
| `FOUNDRY_ACCESS_TIMEOUT_SECONDS` | `180` | Maximum wait for a new deployer role, with immediate access checks |
| `APIM_SECRET_REFRESH_TIMEOUT_SECONDS` | `180` | Maximum wait for APIM to load the current Key Vault webhook secret |
| `INFRA_DEPLOYMENT_ATTEMPTS` | `6` | Bounded retries for eventual-consistency failures during provisioning |
| `INFRA_RETRY_DELAY_SECONDS` | `30` | Delay between infrastructure deployment attempts |
| `RBAC_PROPAGATION_WAIT_SECONDS` | `30` | Wait only after creating data-plane assignments |

Choose a model/version/SKU available in the selected region and subscription. To use a service principal, set
`DEPLOYER_OBJECT_ID` and `DEPLOYER_PRINCIPAL_TYPE=ServicePrincipal` when automatic discovery is unsuitable.

### Rotate the webhook secret

Normal redeployments reuse the existing Key Vault secret. Rotate it explicitly with:

```bash
ROTATE_TELEGRAM_WEBHOOK_SECRET=1 ./deploy.sh
```

The Bicep deployment creates a new secret version, APIM's versionless Key Vault reference follows it, and the final
step registers the same new value with Telegram.

## How requests flow

1. Telegram sends an authenticated HTTPS webhook to APIM.
2. APIM compares `X-Telegram-Bot-Api-Secret-Token` with a Key Vault-backed named value, removes the caller-controlled
   header, and stamps an internal ingress header from the same named value.
3. The policy reads the original JSON object, adds only the top-level `channel: "telegram"` discriminator, and
   preserves the Telegram update fields.
4. It extracts the chat id from `message`, `edited_message`, or `callback_query.message`, sets it as
   `agent_session_id`, and authenticates to Foundry with APIM's managed identity.
5. The hosted handler authenticates the internal ingress header, validates and dispatches `channel`, and requires the
   APIM-provided session id to match the Telegram chat id before using it for the `AgentSession` and Cosmos history
   partition.

One bot is deployed per sample environment, so the chat-derived session key is scoped by that environment.
`/new` clears that Cosmos history without invoking the model. `/start` and `/help` are also handled in application
code. Callback queries are acknowledged before their data is processed.

For photos, PDF documents, and MP3 or WAV audio, the agent calls Telegram `getFile`, rejects files over 1 MiB,
downloads the bytes, and creates an inline data URI. The conservative limit leaves room for base64 and Cosmos DB
item serialization overhead. Voice notes, video, and unsupported document/audio formats are rejected before model
invocation. A token-bearing Telegram file URL is never sent to the model. Captions remain text input when supported
media cannot be resolved.

Agent execution is streaming-only. The bot sends a placeholder, consumes a `ResponseStream`, throttles cumulative
`editMessageText` calls, and ignores only Telegram's idempotent “message is not modified” error. Final image
operations are preserved; an image-only response deletes the placeholder before sending the image. The Invocations
request stays open until streaming and Telegram delivery finish.

The agent configures the Azure Monitor OpenTelemetry exporter from the Foundry project's Application Insights
connection. Sensitive GenAI telemetry is enabled by default, so model spans can include prompts, responses, and
tool arguments/results. Set `ENABLE_SENSITIVE_DATA=false` before deployment when that content must not be collected.
The deployment grants the hosted-agent identity account-scoped `Foundry User` access so it can resolve that
connection. Content-bearing Agent Framework and HTTP client INFO logs remain suppressed.

## Validate

After deployment:

1. Send `/start`, `/help`, and a normal text message.
2. Ask a follow-up to verify durable context.
3. Send `/new`, then verify the previous topic is no longer remembered.
4. Send a captioned image and an inline-button callback.
5. Review traces in the deployed Application Insights resource.

Focused mocked tests require no Azure resources or Telegram bot:

```bash
uv sync --group dev
uv run --group dev pytest -q
uv run --group dev ruff check main.py tests
uv run --group dev pyright
```

## Production limitations

- Telegram waits synchronously while the model streams and messages are edited. Foundry/APIM/backend timeouts can
  cause Telegram retries even after partial side effects.
- Updates are not deduplicated by `update_id`; there is no queue, dead-letter path, or durable delivery workflow.
- Retry and rate-limit handling is intentionally basic.
- Public endpoints are enabled; the sample does not configure private networking or an allowlist.
- There is no distributed per-chat lock, so concurrent updates can race across hosted instances.
- APIM maps all users in a group to the shared chat id. Add authorization before exposing sensitive tools or data.
- Sensitive telemetry is enabled for demonstration. Disable it for workloads whose prompts, responses, tool data,
  or attachments must not be stored in Application Insights.
- Foundry hosted sessions are pinned to the agent version that created them. After deploying a new version, delete
  an existing hosted session before testing that chat against the new version; Cosmos conversation history is
  stored separately.

For a production system, acknowledge into a durable queue, deduplicate and serialize per chat, process
asynchronously, implement bounded retries and `429` handling, and apply the required network controls.

## Cleanup

Set the same configuration used for deployment, then run:

```bash
export TELEGRAM_BOT_TOKEN="<bot-token>"
./remove.sh
```

The deployment refuses to adopt an existing resource group unless it carries this sample's ownership tag. The removal
script verifies the same tag before unregistering the webhook or deleting the dedicated resource group, and then
verifies that Telegram removed the webhook before deletion. It uses the same `NAME_PREFIX`, `RESOURCE_GROUP_NAME`, and
`AZURE_SUBSCRIPTION_ID` defaults and overrides as `deploy.sh`. The bot token is read only from the current shell, and
the script does not print the token or Telegram response.

To also remove the local azd environment after the resource group is gone:

```bash
azd env delete "${AZD_ENV_NAME:-${NAME_PREFIX:-telegramagent}-telegram}" --force
```
