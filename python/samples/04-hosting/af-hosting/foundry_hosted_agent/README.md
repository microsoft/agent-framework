# foundry_hosted_agent — Responses + Invocations (Foundry Hosted Agents compatible)

Smallest end-to-end hosting sample. One Foundry-backed agent, two
channels, no human-chat surface — and that minimal shape is the whole
point: per
[ADR 0026 §11](../../../../../docs/decisions/0026-hosting-channels.md), a
host configured with at least the **Responses** and **Invocations**
channels under their default mount roots is **runtime-compatible with
the Foundry Hosted Agents platform**. The same container image runs
locally, behind any ASGI server, or as a Hosted Agent — no protocol
shim, no extra adapter.

| Route                          | Channel              | Used by                                     |
| ------------------------------ | -------------------- | ------------------------------------------- |
| `POST /responses`              | `ResponsesChannel`   | OpenAI Responses clients (`call_server.py`) |
| `POST /invocations/invoke`     | `InvocationsChannel` | Host-native JSON envelope (Hosted Agents)   |

## Conversation history

The agent is wired with `FoundryHostedAgentHistoryProvider` (from
`agent-framework-foundry-hosting`). When a Responses request supplies
`previous_response_id`, the channel uses it as the session id and the
provider fetches the prior turn chain directly from
`{FOUNDRY_PROJECT_ENDPOINT}/storage/...` using the same managed-identity
credential as the chat client. Locally (when `FOUNDRY_HOSTING_ENVIRONMENT`
is unset) it transparently falls back to an in-memory store, so the same
code runs in dev. Writes are a no-op — Foundry persists Responses turns
authoritatively as the runtime executes them.

For richer scenarios (custom tools, history providers, run hooks,
multicast, Telegram, Teams, identity linking) see
[`../local_telegram`](../local_telegram) and
[`../local_identity_link`](../local_identity_link).

## Layout

```
foundry_hosted_agent/
├── app.py                       # the host (ResponsesChannel + InvocationsChannel)
├── call_server.py               # client: openai SDK / agent framework / FoundryAgent
├── agent.yaml                   # Foundry Hosted Agents minimal definition
├── agent.manifest.yaml          # Foundry Hosted Agents full deployment manifest
├── azure.yaml                   # azd service config (build context = python/)
├── Dockerfile                   # built from python/ workspace root, mirrors the repo layout
├── Dockerfile.dockerignore      # BuildKit allowlist that trims the context
├── workspace.pyproject.toml     # minimal workspace stub copied into the image
├── pyproject.toml               # in-tree editable workspace deps
└── README.md                    # this file
```

## Run locally

```bash
export FOUNDRY_PROJECT_ENDPOINT=https://<your-project>.services.ai.azure.com
export MODEL_DEPLOYMENT_NAME=gpt-4.1-mini
az login                       # any DefaultAzureCredential source

uv sync
uv run python app.py           # binds 0.0.0.0:8000
```

The env var names match `agent.manifest.yaml` so the same shell
environment works for both local runs and Hosted Agent deployments.

## Call locally

```bash
uv sync --group dev

# OpenAI SDK pointed at the local /responses endpoint.
uv run python call_server.py --via openai "hello there"

# The same call via the Agent Framework Agent + OpenAIChatClient stack.
uv run python call_server.py --via af "hello there"

# Once deployed as a Hosted Agent: target the Foundry-managed endpoint.
export FOUNDRY_HOSTED_AGENT_NAME=agent-framework-hosting-sample
uv run python call_server.py --via foundry "hello there"
```

## Docker

The Docker build context is the **`python/` workspace root**, not this
sample folder, because `pyproject.toml` resolves the in-tree
`agent-framework-hosting*` packages via editable workspace path sources
(`../../../../packages/...`). The Dockerfile mirrors the repo layout
inside the image so those paths and the committed `uv.lock` resolve
unchanged. A `Dockerfile.dockerignore` (BuildKit) trims the upload to
just the four packages the image needs (`core`, `hosting`,
`hosting-invocations`, `hosting-responses`) plus this sample, and
`workspace.pyproject.toml` is copied as `/repo/python/pyproject.toml` —
a minimal workspace root that only references the four members actually
present (the real workspace root declares ~36 members and uv would
otherwise fail metadata generation for the missing ones).

```bash
# From the sample folder — context = python/ workspace root.
DOCKER_BUILDKIT=1 docker build \
    -f Dockerfile \
    -t hosting-sample-hosted-agent \
    ../../../..

docker run -p 8000:8000 \
    -e FOUNDRY_PROJECT_ENDPOINT -e MODEL_DEPLOYMENT_NAME \
    -e AZURE_CLIENT_ID -e AZURE_TENANT_ID -e AZURE_CLIENT_SECRET \
    hosting-sample-hosted-agent
```

## Hosted Agent deployment

`azure.yaml` keeps `project: .` (azd's project model expects the
service to live under the azd root) but sets
`docker.context: ../../../..` so the Docker build sees the `python/`
workspace root — same widening as the manual `docker build` above, just
expressed in azd terms. `docker.remoteBuild` is **off**: remote build
ships only the project folder, which would miss the workspace
packages. Once the in-tree `agent-framework-hosting*` packages are
published to PyPI this can flip back to `remoteBuild: true` with the
default narrow context.

The two YAMLs follow the same convention as the
[`foundry-hosted-agents/`](../../foundry-hosted-agents/) reference
samples — `agent.yaml` is the minimal kind/protocols/resources card,
`agent.manifest.yaml` is the full template + environment-variable +
model-resource binding used during deployment.

```bash
azd up        # provisions infra/ + builds + pushes + deploys
azd deploy    # rebuild + redeploy only
```

### Required Foundry RBAC

The container runs as the Hosted Agent's managed identity. That identity
needs permission to call the Foundry project's agent/Responses endpoints
— without it the call returns 401 ``PermissionDenied``. Grant the
**Azure AI Project Manager** role (or the more granular
``Microsoft.CognitiveServices/accounts/AIServices/agents/*`` data
actions) on the Foundry project to the Hosted Agent's managed identity.
See <https://aka.ms/FoundryPermissions> for the full role list.

### Health probe

The Foundry Hosted Agents runtime probes ``GET /readiness``;
``AgentFrameworkHost`` exposes that route automatically (returns
``200 ok``). No extra wiring needed.

The host code never imports anything Foundry-specific beyond the chat
client itself — swapping `FoundryChatClient` for `OpenAIChatClient` (or
any other client) flips this sample from a Hosted Agent target to a
non-Foundry deployment without touching the channels.
