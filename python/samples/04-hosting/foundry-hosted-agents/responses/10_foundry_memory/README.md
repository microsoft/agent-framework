# What this sample demonstrates

An [Agent Framework](https://github.com/microsoft/agent-framework) agent with persistent semantic memory backed by an **Azure AI Foundry Memory Store**, hosted using the **Responses protocol**. The agent remembers facts the user has shared (e.g., dietary preferences, name) across sessions by retrieving and updating memories around every model invocation via `FoundryMemoryProvider`.

## How It Works

### Model Integration

The agent uses `FoundryChatClient` from the Agent Framework to create a Responses client from the project endpoint and model deployment. `allow_preview=True` is passed so the same `AIProjectClient` can also call the preview `beta.memory_stores` API.

### Memory via Foundry Memory Store

`FoundryMemoryProvider` is wired into the agent as a context provider. Around each model invocation it:

1. **Retrieves user-profile memories** for the configured `scope` (e.g., user id) on the first turn of a session.
2. **Searches for contextual memories** matching the current user message and injects them into the model context.
3. **Updates the store** with new facts inferred from the conversation.

Crucially, the provider is constructed with `project_client=client.project_client` — i.e. it reuses the `AIProjectClient` that `FoundryChatClient` already created, instead of allocating a second one. This keeps a single authentication context and connection pool for both chat and memory operations.

See [main.py](main.py) for the full implementation.

### Agent Hosting

The agent is hosted using the [Agent Framework](https://github.com/microsoft/agent-framework) with the `ResponsesHostServer`, which provisions a REST API endpoint compatible with the OpenAI Responses protocol.

## Prerequisites

- An Azure AI Foundry project with:
  - A deployed chat model (e.g., `gpt-4.1-mini`)
  - A deployed embedding model (e.g., `text-embedding-3-small`) — used by the memory store itself, not by the agent at runtime
- Azure CLI logged in (`az login`)

### Required RBAC

Your identity (or the Managed Identity running the container in production) needs **Azure AI User** on the Foundry project scope. This single role covers both provisioning the memory store with `provision_memory_store.py` and reading/writing memories from `main.py`.

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

## Interacting with the agent

> Depending on how you run the agent host, you can invoke the agent using `curl` (`Invoke-WebRequest` in PowerShell) or `azd`. Please refer to the [parent README](../../README.md) for more details.

Send a POST request to the server with a JSON body containing an `"input"` field to interact with the agent. The first request seeds a memory; subsequent requests (especially in new sessions) should be able to recall it because memories are persisted across Foundry Hosted Agents sessions.

> In this sample, the memory is scoped to the user by specifying `scope="{{$userId}}"`, thus memories are isolated across different users but shared across different sessions from the same user.

```bash
# 1. Tell the agent something to remember.
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" \
  -d '{"input": "I prefer dark roast coffee and I am allergic to nuts."}'

# Wait a few seconds for the memory to be stored, then start a fresh conversation:
curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" \
  -d '{"input": "Can you recommend a coffee and a snack for me?"}'

curl -X POST http://localhost:8088/responses -H "Content-Type: application/json" \
  -d '{"input": "What do you remember about my preferences?"}'
```

## Deploying the Agent to Foundry

To host the agent on Foundry, follow the instructions in the [Deploying the Agent to Foundry](../../README.md#deploying-the-agent-to-foundry) section of the README in the parent directory.

When deploying, make sure `MEMORY_STORE_NAME` and `FOUNDRY_MEMORY_SCOPE` are set in your `azd` environment so they get injected into the hosted container per [`agent.manifest.yaml`](agent.manifest.yaml):

```bash
azd env set MEMORY_STORE_NAME "agent_framework_memory"
```

If these are not set, running `azd ai agent init -m <agent-manifest.yaml>` will prompt you to enter them interactively.

The deployed agent's Managed Identity needs **Azure AI User** on the Foundry project to read and write memories at runtime. Make sure you have run `provision_memory_store.py` against the same Foundry project before deploying — otherwise the agent will fail on the first turn when it tries to read from a non-existent store.
