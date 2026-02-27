# Hosted Agent Samples

These samples demonstrate how to build and deploy **code-based hosted agents** using the [Azure AI AgentServer SDK](https://www.nuget.org/packages/Azure.AI.AgentServer.AgentFramework/). Each sample can run locally and be deployed to Microsoft Foundry.

## Samples

| Sample | Description |
|--------|-------------|
| [`AgentsInWorkflows`](./AgentsInWorkflows/) | Translation workflow with 3 sequential agents (French → Spanish → English) using `WorkflowBuilder` |
| [`AgentWithHostedMCP`](./AgentWithHostedMCP/) | Agent with Hosted MCP server integration for Microsoft Learn documentation search |
| [`AgentWithTextSearchRag`](./AgentWithTextSearchRag/) | RAG pattern using `TextSearchProvider` for pre-invocation document search with source citations |
| [`FoundryMultiAgent`](./FoundryMultiAgent/) | Multi-agent Writer-Reviewer workflow using `AIProjectClient.CreateAIAgentAsync()` from [Microsoft.Agents.AI.AzureAI](https://www.nuget.org/packages/Microsoft.Agents.AI.AzureAI/) |
| [`FoundrySingleAgent`](./FoundrySingleAgent/) | Single agent with local C# tool execution (hotel search) using `AIProjectClient.CreateAIAgentAsync()` from [Microsoft.Agents.AI.AzureAI](https://www.nuget.org/packages/Microsoft.Agents.AI.AzureAI/) |

## Prerequisites

- .NET 10.0 SDK or later
- Azure AI Foundry Project with a deployed chat model
- Azure CLI (`az login`)
- **Azure AI Developer** role on the Foundry resource (for samples using `CreateAIAgentAsync`)

See each sample's README for specific setup instructions.
