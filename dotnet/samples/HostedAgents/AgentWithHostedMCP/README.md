# What this sample demonstrates

This sample demonstrates how to use a Hosted Model Context Protocol (MCP) server with an AI agent.
The agent connects to the Microsoft Learn MCP server to search documentation and answer questions using official Microsoft content.

Key features:
- Configuring MCP tools with automatic approval (no user confirmation required)
- Filtering available tools from an MCP server
- Using Azure OpenAI Responses with MCP tools

## Prerequisites

Before running this sample, ensure you have:

1. An Azure OpenAI endpoint configured
2. A deployment of a chat model (e.g., gpt-4o-mini)
3. Azure CLI installed and authenticated

**Note**: This sample uses Azure CLI credentials for authentication. Make sure you're logged in with `az login` and have access to the Azure OpenAI resource.

## Environment Variables

Set the following environment variables:

```powershell
# Replace with your Azure OpenAI endpoint
$env:AZURE_OPENAI_ENDPOINT="https://your-openai-resource.openai.azure.com/"

# Optional, defaults to gpt-4o-mini
$env:AZURE_OPENAI_DEPLOYMENT_NAME="gpt-4o-mini"
```

## How It Works

The sample connects to the Microsoft Learn MCP server and uses its documentation search capabilities:

1. The agent is configured with a HostedMcpServerTool pointing to `https://learn.microsoft.com/api/mcp`
2. Only the `microsoft_docs_search` tool is enabled from the available MCP tools
3. Approval mode is set to `NeverRequire`, allowing automatic tool execution
4. When you ask questions, Azure OpenAI Responses automatically invokes the MCP tool to search documentation
5. The agent returns answers based on the Microsoft Learn content

In this configuration, the OpenAI Responses service manages tool invocation directly - the Agent Framework does not handle MCP tool calls.
