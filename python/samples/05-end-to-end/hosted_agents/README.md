# Hosted Agent Samples

These samples demonstrate how to build and deploy **code-based hosted agents** using the [Azure AI AgentServer SDK](https://pypi.org/project/azure-ai-agentserver-agentframework/). Each sample can run locally and be deployed to Microsoft Foundry.

## Samples

| Sample | Description |
|--------|-------------|
| [`agents_in_workflow`](./agents_in_workflow/) | Translation workflow with 3 sequential agents (French → Spanish → English) |
| [`agent_with_hosted_mcp`](./agent_with_hosted_mcp/) | Agent with Hosted MCP server integration for Microsoft Learn documentation search |
| [`agent_with_text_search_rag`](./agent_with_text_search_rag/) | RAG pattern with text search for pre-invocation document retrieval |
| [`foundry_multiagent`](./foundry_multiagent/) | Multi-agent Writer-Reviewer workflow using Azure AI Foundry agents |
| [`foundry_single_agent`](./foundry_single_agent/) | Single agent with local tool execution (hotel search) using Azure AI Foundry |

## Prerequisites

- Python 3.10 or later
- Azure AI Foundry Project with a deployed chat model
- Azure CLI (`az login`)

See each sample's README for specific setup instructions.
