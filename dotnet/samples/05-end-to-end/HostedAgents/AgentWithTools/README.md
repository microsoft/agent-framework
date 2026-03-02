# What this sample demonstrates

This sample demonstrates how to use Foundry tools with an AI agent via the `UseFoundryTools` extension. The agent is configured with two tool types: an MCP (Model Context Protocol) connection for fetching Microsoft Learn documentation and a code interpreter for running code when needed.

Key features:

- Configuring Foundry tools using `UseFoundryTools` with MCP and code interpreter
- Connecting to an external MCP tool via a Foundry project connection
- Using `AzureCliCredential` for Azure authentication
- OpenTelemetry instrumentation for both the chat client and agent

> For common prerequisites and setup instructions, see the [Hosted Agent Samples README](../README.md).

## Prerequisites

In addition to the common prerequisites:

1. An **Azure AI Foundry project** with a chat model deployed (e.g., `gpt-5.2`, `gpt-4o-mini`)
2. The **Azure AI Developer** role assigned on the Foundry resource (includes the `agents/write` data action required by `UseFoundryTools`)
3. An **MCP tool connection** configured in your Foundry project pointing to `https://learn.microsoft.com/api/mcp`

## Environment Variables

In addition to the common environment variables in the root README:

```powershell
# Your Azure AI Foundry project endpoint (required by UseFoundryTools)
$env:AZURE_AI_PROJECT_ENDPOINT="https://your-resource.services.ai.azure.com/api/projects/your-project"

# Chat model deployment name (defaults to gpt-4o-mini if not set)
$env:AZURE_OPENAI_DEPLOYMENT_NAME="gpt-4o-mini"

# The MCP tool connection name (just the name, not the full ARM resource ID)
$env:MCP_TOOL_CONNECTION_ID="SampleMCPTool"
```

## How It Works

1. An `AzureOpenAIClient` is created with `AzureCliCredential` and used to get a chat client
2. The chat client is wrapped with `UseFoundryTools` which registers two Foundry tool types:
   - **MCP connection**: Connects to an external MCP server (Microsoft Learn) via the project connection name, providing documentation fetch and search capabilities
   - **Code interpreter**: Allows the agent to execute code snippets when needed
3. `UseFoundryTools` resolves the connection using `AZURE_AI_PROJECT_ENDPOINT` internally
4. A `ChatClientAgent` is created with instructions guiding it to use the MCP tools for documentation queries
5. The agent is hosted using `RunAIAgentAsync` which exposes the OpenAI Responses-compatible API endpoint
