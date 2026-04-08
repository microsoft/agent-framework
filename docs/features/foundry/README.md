# Azure AI Foundry Integration

## Overview

The Agent Framework provides two primary integration points for Azure AI Foundry:

| Class | Purpose | When to Use |
| --- | --- | --- |
| `FoundryAgent` / `RawFoundryAgent` | Connect to **existing** Foundry agents | When you want to use an agent that's already configured in Foundry (PromptAgent or HostedAgent) |
| `FoundryChatClient` / `RawFoundryChatClient` | Create a chat client for **model deployments** | When you want direct chat access to a model through Foundry without using a pre-configured agent |

## Key Differences

### FoundryAgent — Connect to Existing Agents

Use `FoundryAgent` (recommended) when:

- You have an existing **PromptAgent** or **HostedAgent** in Foundry
- You want the agent's predefined behavior, tools, and instructions
- You need agent-level middleware, telemetry, and function invocation support

Use `RawFoundryAgent` when:

- You want the lower-level agent wrapper without agent-level middleware/telemetry layers
- You want to provide a custom client via `client_type` parameter

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

Use `FoundryChatClient` (recommended) when:

- You want to chat directly with a model deployment through Foundry
- You don't need a pre-configured agent — you provide the instructions
- You want full control over the chat interaction
- You need chat middleware, telemetry, and function invocation support

Use `RawFoundryChatClient` when:

- You want the lower-level chat client without wrapper layers
- You want to build a custom client via subclassing

**Required parameters:**
- `project_endpoint` — The Foundry project endpoint URL
- `model` — The model deployment name
- `credential` — Azure credential for authentication

**Example:**
```python
from agent_framework import Message
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential

client = FoundryChatClient(
    project_endpoint="https://your-project.services.ai.azure.com",
    model="gpt-4o",
    credential=AzureCliCredential(),
)

response = await client.get_response(messages=[Message(user_content="Hello!")])
print(response.text)
```

## When to Use Each

| Scenario | Recommended Class |
| --- | --- |
| Use a PromptAgent configured in Foundry with specific instructions, tools, and behavior | `FoundryAgent` |
| Use a HostedAgent (custom runtime agent) in Foundry | `FoundryAgent` |
| Chat directly with a model deployment without an agent wrapper | `FoundryChatClient` |
| Build a custom agent experience with your own instructions | `FoundryChatClient` + `Agent` |
| Need full middleware/telemetry support | Use `FoundryAgent` or `FoundryChatClient` (not raw variants) |
| Need minimal overhead, custom client subclass | Use `RawFoundryChatClient`, or for agent connections provide a raw agent chat client via `client_type=RawFoundryAgentChatClient` |

## Raw vs. Recommended Variants

Each class has both a **raw** and **recommended** variant:

| Recommended | Raw | Description |
| --- | --- | --- |
| `FoundryAgent` | `RawFoundryAgent` | Connects to an existing Foundry agent, but without the additional **agent-level** middleware and telemetry layers that `FoundryAgent` adds |
| `FoundryChatClient` | `RawFoundryChatClient` | Chat client variant without the recommended wrapper's middleware and telemetry layers |

The raw variants are lower-level building blocks, but they are not identical:

- `RawFoundryAgent` still defaults to an internal client stack that includes function invocation, chat middleware, and chat telemetry. Compared to `FoundryAgent`, it omits the extra **agent-level** middleware and telemetry layers.
- `RawFoundryChatClient` is the lower-level chat client variant when you do not want the recommended wrapper layers.

If you truly need a raw Foundry agent chat client, use `client_type=RawFoundryAgentChatClient`.

Use raw variants when you need lower-level control or want to build a custom client composition via subclassing.

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