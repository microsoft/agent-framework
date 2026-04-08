# Azure AI Foundry Integration

## Overview

The Agent Framework provides two primary integration points for Azure AI Foundry:

| Class | Purpose | When to Use |
| --- | --- | --- |
| `FoundryAgent` / `RawFoundryAgent` | Connect to **existing** Foundry agents | When you want to use an agent that's already configured in Foundry (PromptAgent or HostedAgent) |
| `FoundryChatClient` / `RawFoundryChatClient` | Create a chat client for **model deployments** | When you want direct chat access to a model through Foundry without using a pre-configured agent |

## Key Differences

### FoundryAgent — Connect to Existing Agents

Use `FoundryAgent` (recommended) or `RawFoundryAgent` when:

- You have an existing **PromptAgent** or **HostedAgent** in Foundry
- You want the agent's predefined behavior, tools, and instructions
- You need middleware, telemetry, and function invocation support

**Required parameters:**
- `project_endpoint` — The Foundry project endpoint URL
- `agent_name` — The name of the existing Foundry agent to connect to
- `agent_version` — Required for PromptAgents, optional for HostedAgents
- `credential` — Azure credential for authentication

**Example:**
```python
from agent_framework.foundry import FoundryAgent
from azure.identity import AzureCliCredential

# Connect to a PromptAgent
agent = FoundryAgent(
    project_endpoint="https://your-project.services.ai.azure.com",
    agent_name="my-prompt-agent",
    agent_version="1.0",
    credential=AzureCliCredential(),
)
result = await agent.run("Hello!")

# Connect to a HostedAgent (no version needed)
agent = FoundryAgent(
    project_endpoint="https://your-project.services.ai.azure.com",
    agent_name="my-hosted-agent",
    credential=AzureCliCredential(),
)
```

### FoundryChatClient — Direct Model Access

Use `FoundryChatClient` (recommended) or `RawFoundryChatClient` when:

- You want to chat directly with a model deployment through Foundry
- You don't need a pre-configured agent — you provide the instructions
- You want full control over the chat interaction

**Required parameters:**
- `project_endpoint` — The Foundry project endpoint URL
- `model` — The model deployment name
- `credential` — Azure credential for authentication

**Example:**
```python
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential

client = FoundryChatClient(
    project_endpoint="https://your-project.services.ai.azure.com",
    model="gpt-4o",
    credential=AzureCliCredential(),
)

response = await client.complete(messages=["Hello!"])
print(response.message.content)
```

## When to Use Each

| Scenario | Recommended Class |
| --- | --- |
| Use a PromptAgent configured in Foundry with specific instructions, tools, and behavior | `FoundryAgent` |
| Use a HostedAgent (custom runtime agent) in Foundry | `FoundryAgent` |
| Chat directly with a model deployment without an agent wrapper | `FoundryChatClient` |
| Build a custom agent experience with your own instructions | `FoundryChatClient` + `Agent` |
| Need full middleware/telemetry support | Use `FoundryAgent` or `FoundryChatClient` (not raw variants) |
| Need minimal overhead, custom client subclass | Use `RawFoundryAgent` or `RawFoundryChatClient` |

## Raw vs. Recommended Variants

Each class has both a **raw** and **recommended** variant:

| Recommended | Raw | Description |
| --- | --- | --- |
| `FoundryAgent` | `RawFoundryAgent` | Agent wrapper with full middleware and telemetry |
| `FoundryChatClient` | `RawFoundryChatClient` | Chat client with full middleware and telemetry |

The raw variants (`RawFoundryAgent`, `RawFoundryChatClient`) omit:
- Chat or agent middleware layers
- Telemetry (OpenTelemetry)
- Function invocation support

Use raw variants when you need to build a custom client with specific middleware layers via subclassing.

## Environment Variables

Both integrations support environment variable configuration:

| Variable | Used By | Description |
| --- | --- | --- |
| `FOUNDRY_PROJECT_ENDPOINT` | Both | Foundry project endpoint URL |
| `FOUNDRY_AGENT_NAME` | `FoundryAgent` | Name of the Foundry agent |
| `FOUNDRY_AGENT_VERSION` | `FoundryAgent` | Version of the agent (PromptAgents) |
| `FOUNDRY_MODEL` | `FoundryChatClient` | Model deployment name |

## Packages

| Package | Source |
| --- | --- |
| `agent-framework-foundry` | [`python/packages/foundry`](../../../python/packages/foundry) |