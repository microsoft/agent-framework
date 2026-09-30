# What this sample demonstrates

An [Agent Framework](https://github.com/microsoft/agent-framework) agent with persistent semantic memory backed by a **Microsoft Foundry Memory Store**, hosted using the **Responses protocol**. The agent remembers facts the user has shared (e.g., dietary preferences, name) across sessions by retrieving and updating memories around every model invocation via `FoundryMemoryProvider`.

## How It Works

### Model Integration

The agent uses `FoundryChatClient` from the Agent Framework to create a Responses client from the project endpoint and model deployment. `allow_preview=True` is passed so the same `AIProjectClient` can also call the preview `beta.memory_stores` API.

### Memory via Foundry Memory Store

`FoundryMemoryProvider` is wired into the agent as a context provider. Around each model invocation it:

1. **Retrieves user-profile memories** for the configured `scope` (e.g., user id) on the first turn of a session.
2. **Searches for contextual memories** matching the current user message and injects them into the model context.
3. **Updates the store** with new facts inferred from the conversation.

The zero-argument `create_agent` factory builds a new agent, credential, project
client and Memory provider **inside each request**. Chat and Memory share that
request's project client, not a process-wide client. Its headers capture the
current platform call ID for both Memory and model calls; raw user IDs are not
forwarded. The request-owned client's context manager closes its own OpenAI and
project transports and credential on completion or cancellation. It does not
change ownership of developer-supplied clients elsewhere in the framework.

The Memory namespace is a framed hash of the **trusted platform user ID**. It
intentionally excludes the sandbox, conversation, MAF session and call IDs: the
same user shares long-term memories across their hosted sessions, while other
users have different namespaces. The host still validates the platform sandbox
and requires a trusted user and call ID before constructing the integration.
Caller model options cannot choose that namespace, and literal template strings
such as `{{$userId}}` are **not** substituted by the framework.

`history_source="agent_server"` supplies conversation history from the outer
Responses service and disables inner model storage. This is separate from
application-owned long-term Memory: outer `store=false` disables host-managed
state, **not** the Memory provider's deliberate read/write side effects. Apply
your application's consent and retention policy before enabling Memory.

See [main.py](main.py) for the full implementation.

### Agent Hosting

The agent is hosted using the [Agent Framework](https://github.com/microsoft/agent-framework) with the `ResponsesHostServer`, which provisions a REST API endpoint compatible with the OpenAI Responses protocol.

## Prerequisites

- A Microsoft Foundry project with:
  - A deployed chat model (e.g., `gpt-4.1-mini`)
  - A deployed embedding model (e.g., `text-embedding-3-small`) — used by the memory store itself, not by the agent at runtime
- Azure CLI logged in (`az login`)

### Required RBAC

Your provisioning identity and the deployed agent's managed identity need
**Foundry User** (formerly **Azure AI User**) on the **Foundry project scope**
for the Memory operations used here. Grant at that project, not merely at an
unrelated resource or only at a model deployment. Scope hashes are application
namespaces, not independent RBAC grants: a principal with project-wide access
must be trusted to enforce the application's user mapping.

## Provisioning the memory store (one time)

[`provision_memory_store.py`](provision_memory_store.py) creates a Foundry Memory Store with the user-profile capability enabled (and chat-summary disabled) using `AIProjectClient.beta.memory_stores.create`. It is safe to re-run: if a store with the same name already exists, the script leaves it alone.

From this directory, with the venv activated and `az login` done:

```bash
export FOUNDRY_PROJECT_ENDPOINT="https://<account>.services.ai.azure.com/api/projects/<project>"
export AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-4.1-mini"
export AZURE_AI_EMBEDDING_MODEL_DEPLOYMENT_NAME="text-embedding-3-small"
export MEMORY_STORE_NAME="agent_framework_memory"
python provision_memory_store.py
```

Or in PowerShell:

```powershell
$env:FOUNDRY_PROJECT_ENDPOINT="https://<account>.services.ai.azure.com/api/projects/<project>"
$env:AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-4.1-mini"
$env:AZURE_AI_EMBEDDING_MODEL_DEPLOYMENT_NAME="text-embedding-3-small"
$env:MEMORY_STORE_NAME="agent_framework_memory"
python provision_memory_store.py
```

Expected output (first run):

```text
Creating memory store 'agent_framework_memory'...
Created memory store 'agent_framework_memory' (id=memstore_...).
```

> To delete the store manually, call `project.beta.memory_stores.delete("<name>")` on an `AIProjectClient` constructed with `allow_preview=True`.

## Running the Agent Host

Follow the instructions in the [Running the Agent Host Locally](../../README.md#running-the-agent-host-locally) section of the README in the parent directory to run the agent host.

In addition to the standard environment variables, this sample requires:

```bash
export MEMORY_STORE_NAME="agent_framework_memory"
```

Or in PowerShell:

```powershell
$env:MEMORY_STORE_NAME="agent_framework_memory"
```

You can also place these in a `.env` file next to `main.py` — see [`.env.example`](.env.example).

Local development also requires an explicit `LOCAL_MEMORY_USER_ID`, for example
`local-developer`. It is a **single-user** developer namespace configured by the
host operator, never a hosted fallback. Local `x-agent-user-id`/call-ID headers
are rejected rather than trusted. Local model/Memory calls use
`AzureCliCredential` (`az login`); hosted calls use managed identity. Do not
expose the local mode as a multi-user authenticated service.

## Interacting with the agent

> Depending on how you run the agent host, you can invoke the agent using `curl` (`Invoke-WebRequest` in PowerShell) or `azd`. Please refer to the [parent README](../../README.md) for more details.

Send a POST request to the server with a JSON body containing an `"input"` field to interact with the agent. The first request seeds a memory; subsequent requests (especially in new sessions) should be able to recall it because memories are persisted across Foundry Hosted Agents sessions.

> Hosted memory uses the trusted user-wide hash produced by `memory_scope`.
> Changing a sandbox or starting a fresh conversation does not clear that user's
> long-term memories. Changing the user selects a different namespace.

```bash
# 1. Tell the agent something to remember.
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" \
  -d '{"input": "I prefer dark roast coffee and I am allergic to nuts."}'

# Wait for the asynchronous Memory update (the default debounce is 300 seconds),
# then start a fresh conversation; immediate recall is not guaranteed:
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" \
  -d '{"input": "Can you recommend a coffee and a snack for me?"}'

curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" \
  -d '{"input": "What do you remember about my preferences?"}'
```

## Deploying the Agent to Foundry

To host the agent on Foundry, follow the instructions in the [Deploying the Agent to Foundry](../../README.md#deploying-the-agent-to-foundry) section of the README in the parent directory.

When deploying, make sure `MEMORY_STORE_NAME` is set in your `azd` environment so it gets injected into the hosted container per [`agent.manifest.yaml`](agent.manifest.yaml):

```bash
azd env set MEMORY_STORE_NAME "agent_framework_memory"
```

If these are not set, running `azd ai agent init -m <agent.manifest.yaml>` will prompt you to enter them interactively.

Provision the Memory Store in the **same project** and grant the deployed managed
identity the project-scoped role above. Provisioning, live Memory calls and
deployment need separately configured resources and are not exercised by the
credential-free checks.
