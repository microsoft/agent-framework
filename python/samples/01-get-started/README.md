# Get Started with Agent Framework for Python

This folder contains a progressive set of samples that introduce the core
concepts of **Agent Framework** one step at a time.

## Prerequisites

```bash
pip install agent-framework-foundry
```

Sample 08 additionally requires `agent-framework-azurefunctions --pre`.

### 1. Configure environment variables

The samples read connection settings from environment variables (or a local
`.env` file loaded via `python-dotenv`). The project endpoint has the shape
`https://<account>.services.ai.azure.com/api/projects/<project>` and must
point at a Foundry **project**, not the account root.

```bash
export FOUNDRY_PROJECT_ENDPOINT="https://<account>.services.ai.azure.com/api/projects/<project>"
export FOUNDRY_MODEL="<your-deployment-name>"   # required; must match a deployment on the account
```

Or drop the same keys into `python/samples/.env`:

```dotenv
FOUNDRY_PROJECT_ENDPOINT=https://<account>.services.ai.azure.com/api/projects/<project>
FOUNDRY_MODEL=<your-deployment-name>
```

> `load_dotenv()` walks upward and loads the **first** `.env` it finds, so a
> `python/samples/.env` next to the samples shadows a `python/.env` higher up.
> If a value looks wrong at runtime, edit the nearest `.env` on the path.
> Also note that already-set shell env vars take precedence over `.env` unless
> you pass `load_dotenv(override=True)`.

### 2. Sign in and grant data-plane access

The samples authenticate with `AzureCliCredential`, so first run:

```bash
az login
```

Calling the Foundry project's inference endpoints (Responses, Chat
Completions, etc. under `/api/projects/<project>/openai/v1/...`) requires a
data-plane role on the AI Services account (or the project sub-resource).
The Responses path is served by the **AIServices** RBAC namespace, so the
`Azure AI Developer` role — which does not include
`Microsoft.CognitiveServices/accounts/AIServices/responses/*` — is **not**
sufficient on its own.

Assign one of the following to your user/service principal on the account
`Microsoft.CognitiveServices/accounts/<account>` (or the child
`.../projects/<project>` scope):

| Role | Grants | Notes |
|------|--------|-------|
| `Foundry Project Runtime User` | `Microsoft.CognitiveServices/accounts/AIServices/responses/*` | Minimal role for the Responses API. |
| `Foundry User` | `Microsoft.CognitiveServices/*` | Broader; covers all Foundry data-plane calls. |

Example (account scope, broad role):

```bash
az role assignment create \
  --assignee "<your-object-id>" \
  --role "Foundry User" \
  --scope "/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<account>"
```

Role propagation can take up to a few minutes. Symptoms of missing/insufficient
roles:

- `401 Unauthorized` — token audience wrong or no role at all.
- `403 PermissionDenied` on the project URL — a role is assigned but its
  `dataActions` don't cover `AIServices/responses/*`.
- `404 DeploymentNotFound` — auth is OK but `FOUNDRY_MODEL` doesn't match any
  deployment on the account. Verify with
  `az cognitiveservices account deployment list -g <rg> -n <account>`.

## Samples

| # | File | What you'll learn |
|---|------|-------------------|
| 1 | [01_hello_agent.py](01_hello_agent.py) | Create your first agent and run it (streaming and non-streaming). |
| 2 | [02_add_tools.py](02_add_tools.py) | Define a function tool with `@tool` and attach it to an agent. |
| 3 | [03_multi_turn.py](03_multi_turn.py) | Keep conversation history across turns with `AgentSession`. |
| 4 | [04_memory.py](04_memory.py) | Add dynamic context with a custom `ContextProvider`. |
| 5 | [05_functional_workflow_with_agents.py](05_functional_workflow_with_agents.py) | Call agents inside a functional workflow. |
| 6 | [06_functional_workflow_basics.py](06_functional_workflow_basics.py) | Write a workflow as a plain async function. |
| 7 | [07_first_graph_workflow.py](07_first_graph_workflow.py) | Chain executors into a graph workflow with edges. |

To host agents and workflows with Durable Task or Azure Functions, continue with the [Durable Agent Framework extension samples](https://github.com/microsoft/agent-framework-durable-extension/tree/main/python/samples).

Run any sample with:

```bash
python 01_hello_agent.py
```

These samples use Azure Foundry models with the Responses API. To switch providers, just replace the client, see [all providers](../02-agents/providers/README.md)
