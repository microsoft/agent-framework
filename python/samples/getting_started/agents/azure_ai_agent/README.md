# Azure AI Agent Examples

This folder contains examples demonstrating different ways to create and use agents with Azure AI using the `AzureAIAgentsProvider` from the `agent_framework.azure` package. These examples use the `azure-ai-agents` 1.x (V1) API surface. For updated V2 (`azure-ai-projects` 2.x) samples, see the [Azure AI V2 examples folder](../azure_ai/).

## Provider Pattern

All examples in this folder use the `AzureAIAgentsProvider` class which provides a high-level interface for agent operations:

- **`create_agent()`** - Create a new agent on the Azure AI service
- **`get_agent()`** - Retrieve an existing agent by ID or from a pre-fetched Agent object
- **`as_agent()`** - Wrap an SDK Agent object as a ChatAgent without HTTP calls

```python
from agent_framework.azure import AzureAIAgentsProvider
from azure.identity.aio import AzureCliCredential

async with (
    AzureCliCredential() as credential,
    AzureAIAgentsProvider(credential=credential) as provider,
):
    agent = await provider.create_agent(
        name="MyAgent",
        instructions="You are a helpful assistant.",
        tools=my_function,
    )
    result = await agent.run("Hello!")
```

## Examples

| File | Description |
|------|-------------|
| [`azure_ai_provider_methods.py`](azure_ai_provider_methods.py) | Comprehensive example demonstrating all `AzureAIAgentsProvider` methods: `create_agent()`, `get_agent()`, `as_agent()`, and managing multiple agents from a single provider. |
| [`azure_ai_basic.py`](azure_ai_basic.py) | The simplest way to create an agent using `AzureAIAgentsProvider`. It automatically handles all configuration using environment variables. Shows both streaming and non-streaming responses. |
| [`azure_ai_with_bing_custom_search.py`](azure_ai_with_bing_custom_search.py) | Shows how to use Bing Custom Search with Azure AI agents to find real-time information from the web using custom search configurations. Demonstrates how to set up and use HostedWebSearchTool with custom search instances. |
| [`azure_ai_with_bing_grounding.py`](azure_ai_with_bing_grounding.py) | Shows how to use Bing Grounding search with Azure AI agents to find real-time information from the web. Demonstrates web search capabilities with proper source citations and comprehensive error handling. |
| [`azure_ai_with_bing_grounding_citations.py`](azure_ai_with_bing_grounding_citations.py) | Demonstrates how to extract and display citations from Bing Grounding search responses. Shows how to collect citation annotations (title, URL, snippet) during streaming responses, enabling users to verify sources and access referenced content. |
| [`azure_ai_with_code_interpreter_file_generation.py`](azure_ai_with_code_interpreter_file_generation.py) | Shows how to retrieve file IDs from code interpreter generated files using both streaming and non-streaming approaches. |
| [`azure_ai_with_code_interpreter.py`](azure_ai_with_code_interpreter.py) | Shows how to use the HostedCodeInterpreterTool with Azure AI agents to write and execute Python code. Includes helper methods for accessing code interpreter data from response chunks. |
| [`azure_ai_with_existing_agent.py`](azure_ai_with_existing_agent.py) | Shows how to work with an existing SDK Agent object using `provider.as_agent()`. This wraps the agent without making HTTP calls. |
| [`azure_ai_with_existing_thread.py`](azure_ai_with_existing_thread.py) | Shows how to work with a pre-existing thread by providing the thread ID. Demonstrates proper cleanup of manually created threads. |
| [`azure_ai_with_explicit_settings.py`](azure_ai_with_explicit_settings.py) | Shows how to create an agent with explicitly configured provider settings, including project endpoint and model deployment name. |
| [`azure_ai_with_azure_ai_search.py`](azure_ai_with_azure_ai_search.py) | Demonstrates how to use Azure AI Search with Azure AI agents. Shows how to create an agent with search tools using the SDK directly and wrap it with `provider.get_agent()`. |
| [`azure_ai_with_file_search.py`](azure_ai_with_file_search.py) | Demonstrates how to use the HostedFileSearchTool with Azure AI agents to search through uploaded documents. Shows file upload, vector store creation, and querying document content. |
| [`azure_ai_with_function_tools.py`](azure_ai_with_function_tools.py) | Demonstrates how to use function tools with agents. Shows both agent-level tools (defined when creating the agent) and query-level tools (provided with specific queries). |
| [`azure_ai_with_hosted_mcp.py`](azure_ai_with_hosted_mcp.py) | Shows how to integrate Azure AI agents with hosted Model Context Protocol (MCP) servers for enhanced functionality and tool integration. Demonstrates remote MCP server connections and tool discovery. |
| [`azure_ai_with_local_mcp.py`](azure_ai_with_local_mcp.py) | Shows how to integrate Azure AI agents with local Model Context Protocol (MCP) servers for enhanced functionality and tool integration. Demonstrates both agent-level and run-level tool configuration. |
| [`azure_ai_with_multiple_tools.py`](azure_ai_with_multiple_tools.py) | Demonstrates how to use multiple tools together with Azure AI agents, including web search, MCP servers, and function tools. Shows coordinated multi-tool interactions and approval workflows. |
| [`azure_ai_with_openapi_tools.py`](azure_ai_with_openapi_tools.py) | Demonstrates how to use OpenAPI tools with Azure AI agents to integrate external REST APIs. Shows OpenAPI specification loading, anonymous authentication, thread context management, and coordinated multi-API conversations. |
| [`azure_ai_with_response_format.py`](azure_ai_with_response_format.py) | Demonstrates how to use structured outputs with Azure AI agents using Pydantic models. |
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

4. For samples using Bing Custom Search (like `azure_ai_with_bing_custom_search.py`), you'll also need:
   ```
   BING_CUSTOM_CONNECTION_ID="your-bing-custom-connection-id"
   BING_CUSTOM_INSTANCE_NAME="your-bing-custom-instance-name"
   ```

   To get your Bing Custom Search connection details:
   - Go to [Azure AI Foundry portal](https://ai.azure.com)
   - Navigate to your project's "Connected resources" section
   - Add a new connection for "Grounding with Bing Custom Search"
   - Copy the connection ID and instance name

### Option 2: Using environment variables directly

Set the environment variables in your shell:

```bash
export AZURE_AI_PROJECT_ENDPOINT="your-project-endpoint"
export AZURE_AI_MODEL_DEPLOYMENT_NAME="your-model-deployment-name"
export BING_CONNECTION_ID="your-bing-connection-id"
export BING_CUSTOM_CONNECTION_ID="your-bing-custom-connection-id"
export BING_CUSTOM_INSTANCE_NAME="your-bing-custom-instance-name"
```

### Required Variables

- `AZURE_AI_PROJECT_ENDPOINT`: Your Azure AI project endpoint (required for all examples)
- `AZURE_AI_MODEL_DEPLOYMENT_NAME`: The name of your model deployment (required for all examples)

### Optional Variables

- `BING_CONNECTION_ID`: Your Bing connection ID (required for `azure_ai_with_bing_grounding.py` and `azure_ai_with_multiple_tools.py`)
- `BING_CUSTOM_CONNECTION_ID`: Your Bing Custom Search connection ID (required for `azure_ai_with_bing_custom_search.py`)
- `BING_CUSTOM_INSTANCE_NAME`: Your Bing Custom Search instance name (required for `azure_ai_with_bing_custom_search.py`)
