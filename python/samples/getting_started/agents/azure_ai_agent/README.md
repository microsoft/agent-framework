# Azure AI Agent Examples

This folder contains examples demonstrating different ways to create and use agents with the Azure AI chat client from the `agent_framework.azure` package.

## Examples

| File | Description |
|------|-------------|
| [`azure_ai_basic.py`](azure_ai_basic.py) | The simplest way to create an agent using `ChatAgent` with `AzureAIAgentClient`. It automatically handles all configuration using environment variables. |
| [`azure_ai_with_bing_grounding.py`](azure_ai_with_bing_grounding.py) | Shows how to use Bing Grounding search with Azure AI agents to find real-time information from the web. Demonstrates web search capabilities with proper source citations and comprehensive error handling. |
| [`azure_ai_with_code_interpreter.py`](azure_ai_with_code_interpreter.py) | Shows how to use the HostedCodeInterpreterTool with Azure AI agents to write and execute Python code. Includes helper methods for accessing code interpreter data from response chunks. |
| [`azure_ai_with_existing_agent.py`](azure_ai_with_existing_agent.py) | Shows how to work with a pre-existing agent by providing the agent ID to the Azure AI chat client. This example also demonstrates proper cleanup of manually created agents. |
| [`azure_ai_with_existing_thread.py`](azure_ai_with_existing_thread.py) | Shows how to work with a pre-existing thread by providing the thread ID to the Azure AI chat client. This example also demonstrates proper cleanup of manually created threads. |
| [`azure_ai_with_explicit_settings.py`](azure_ai_with_explicit_settings.py) | Shows how to create an agent with explicitly configured `AzureAIAgentClient` settings, including project endpoint, model deployment, credentials, and agent name. |
| [`azure_ai_with_azure_ai_search.py`](azure_ai_with_azure_ai_search.py) | Demonstrates how to use Azure AI Search with Azure AI agents to search through indexed data. Shows how to configure search parameters, query types, and integrate with existing search indexes. |
| [`azure_ai_with_file_search.py`](azure_ai_with_file_search.py) | Demonstrates how to use the HostedFileSearchTool with Azure AI agents to search through uploaded documents. Shows file upload, vector store creation, and querying document content. Includes both streaming and non-streaming examples. |
| [`azure_ai_with_function_tools.py`](azure_ai_with_function_tools.py) | Demonstrates how to use function tools with agents. Shows both agent-level tools (defined when creating the agent) and query-level tools (provided with specific queries). |
| [`azure_ai_with_hosted_mcp.py`](azure_ai_with_hosted_mcp.py) | Shows how to integrate Azure AI agents with hosted Model Context Protocol (MCP) servers for enhanced functionality and tool integration. Demonstrates remote MCP server connections and tool discovery. |
| [`azure_ai_with_local_mcp.py`](azure_ai_with_local_mcp.py) | Shows how to integrate Azure AI agents with local Model Context Protocol (MCP) servers for enhanced functionality and tool integration. Demonstrates both agent-level and run-level tool configuration. |
| [`azure_ai_with_multiple_tools.py`](azure_ai_with_multiple_tools.py) | Demonstrates how to use multiple tools together with Azure AI agents, including web search, MCP servers, and function tools. Shows coordinated multi-tool interactions and approval workflows. |
| [`azure_ai_with_openapi_tools.py`](azure_ai_with_openapi_tools.py) | Demonstrates how to use OpenAPI tools with Azure AI agents to integrate external REST APIs. Shows OpenAPI specification loading, anonymous authentication, thread context management, and coordinated multi-API conversations using weather and countries APIs. |
| [`azure_ai_with_thread.py`](azure_ai_with_thread.py) | Demonstrates thread management with Azure AI agents, including automatic thread creation for stateless conversations and explicit thread management for maintaining conversation context across multiple interactions. |

## Environment Variables

Before running the examples, you need to set up your environment variables. You can do this in one of two ways:

### Option 1: Using a .env file (Recommended)

1. Copy the `.env.example` file from the `python` directory to create a `.env` file:
   ```bash
   cp ../../.env.example ../../.env
   ```

2. Edit the `.env` file and add your values:
   ```
   AZURE_AI_PROJECT_ENDPOINT="your-project-endpoint"
   AZURE_AI_MODEL_DEPLOYMENT_NAME="your-model-deployment-name"
   ```

3. For samples using Bing Grounding search (like `azure_ai_with_bing_grounding.py` and `azure_ai_with_multiple_tools.py`), you'll also need:
   ```
   BING_CONNECTION_ID="your-bing-connection-id"
   ```

   To get your Bing connection details:
   - Go to [Azure AI Foundry portal](https://ai.azure.com)
   - Navigate to your project's "Connected resources" section
   - Add a new connection for "Grounding with Bing Search"
   - Copy the ID

### Option 2: Using environment variables directly

Set the environment variables in your shell:

```bash
export AZURE_AI_PROJECT_ENDPOINT="your-project-endpoint"
export AZURE_AI_MODEL_DEPLOYMENT_NAME="your-model-deployment-name"
export BING_CONNECTION_ID="your-bing-connection-id"
```

### Required Variables

- `AZURE_AI_PROJECT_ENDPOINT`: Your Azure AI project endpoint (required for all examples)
- `AZURE_AI_MODEL_DEPLOYMENT_NAME`: The name of your model deployment (required for all examples)

### Optional Variables

- `BING_CONNECTION_ID`: Your Bing connection ID (required for `azure_ai_with_bing_grounding.py` and `azure_ai_with_multiple_tools.py`)
