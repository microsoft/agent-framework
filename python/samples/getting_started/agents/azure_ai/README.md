# Azure AI Agent Examples

This folder contains examples demonstrating different ways to create and use agents with the Azure AI chat client from the `agent_framework.azure` package.

## Examples

| File | Description |
|------|-------------|
| [`azure_ai_basic.py`](azure_ai_basic.py) | The simplest way to create an agent using `ChatAgent` with `AzureAIAgentClient`. It automatically handles all configuration using environment variables. |
| [`azure_ai_with_explicit_settings.py`](azure_ai_with_explicit_settings.py) | Shows how to create an agent with explicitly configured `AzureAIAgentClient` settings, including project endpoint, model deployment, credentials, and agent name. |
| [`azure_ai_with_existing_agent.py`](azure_ai_with_existing_agent.py) | Shows how to work with a pre-existing agent by providing the agent ID to the Azure AI chat client. This example also demonstrates proper cleanup of manually created agents. |
| [`azure_ai_with_function_tools.py`](azure_ai_with_function_tools.py) | Demonstrates how to use function tools with agents. Shows both agent-level tools (defined when creating the agent) and query-level tools (provided with specific queries). |
| [`azure_ai_with_code_interpreter.py`](azure_ai_with_code_interpreter.py) | Shows how to use the HostedCodeInterpreterTool with Azure AI agents to write and execute Python code. Includes helper methods for accessing code interpreter data from response chunks. |
| [`azure_ai_with_local_mcp.py`](azure_ai_with_local_mcp.py) | Shows how to integrate Azure AI agents with Model Context Protocol (MCP) servers for enhanced functionality and tool integration. Demonstrates both agent-level and run-level tool configuration. |
| [`azure_ai_with_thread.py`](azure_ai_with_thread.py) | Demonstrates thread management with Azure AI agents, including automatic thread creation for stateless conversations and explicit thread management for maintaining conversation context across multiple interactions. |

## Environment Variables

Make sure to set the following environment variables before running the examples:

- `AZURE_AZURE_FOUNDRY_PROJECT_ENDPOINT`: Your Azure AI project endpoint
- `AZURE_AZURE_FOUNDRY_MODEL_DEPLOYMENT_NAME`: The name of your model deployment

Optionally, you can set:
- `AZURE_AZURE_FOUNDRY_AGENT_NAME`: The name of your agent, this can also be set programmatically when creating the agent.
