# What this sample demonstrates

This sample demonstrates how to use a Hosted Model Context Protocol (MCP) server with an AI agent
that requires **human-in-the-loop approval** before executing any tool call.

The agent connects to the Microsoft Learn MCP server to search documentation, but unlike the
[AgentWithHostedMCP](../AgentWithHostedMCP) sample (which auto-approves tool calls), this sample
requires explicit approval for every MCP tool invocation.

Key features:
- Configuring MCP tools with required approval (`AlwaysRequire` mode)
- Human-in-the-loop pattern for tool call gating
- Using Azure OpenAI Responses with approval-gated MCP tools

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

The sample connects to the Microsoft Learn MCP server with approval-gated tool calls:

1. The agent is configured with a `HostedMcpServerTool` pointing to `https://learn.microsoft.com/api/mcp`
2. Only the `microsoft_docs_search` tool is enabled from the available MCP tools
3. Approval mode is set to `AlwaysRequire`, meaning every tool call must be explicitly approved
4. When you ask a question, Azure OpenAI Responses requests the MCP tool call and the agent surfaces an approval request to the caller
5. The caller must approve or deny the tool call before the agent proceeds
6. Once approved, the MCP tool executes and the agent returns the answer

In this configuration, the OpenAI Responses service manages tool invocation directly — the Agent Framework does not handle MCP tool calls. The approval gate ensures that no tool call executes without explicit human consent.

## Comparison with AgentWithHostedMCP

| Feature | AgentWithHostedMCP | AgentWithApproval |
|---------|-------------------|-------------------|
| MCP Server | Microsoft Learn | Microsoft Learn |
| Approval Mode | `NeverRequire` | `AlwaysRequire` |
| Tool Execution | Automatic | Requires human approval |
| Use Case | Trusted, automated search | Gated access with oversight |
