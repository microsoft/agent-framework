# Azure OpenAI Agent Examples

This folder contains examples demonstrating different ways to create and use agents with the different Azure OpenAI chat client from the `agent_framework.azure` package.

## Examples

| File | Description |
|------|-------------|
| [`azure_assistants_basic.py`](azure_assistants_basic.py) | The simplest way to create an agent using `Agent` with `AzureOpenAIAssistantsClient`. Shows both streaming and non-streaming responses with automatic assistant creation and cleanup. |
| [`azure_assistants_with_code_interpreter.py`](azure_assistants_with_code_interpreter.py) | Shows how to use `AzureOpenAIAssistantsClient.get_code_interpreter_tool()` with Azure agents to write and execute Python code. Includes helper methods for accessing code interpreter data from response chunks. |
| [`azure_assistants_with_existing_assistant.py`](azure_assistants_with_existing_assistant.py) | Shows how to work with a pre-existing assistant by providing the assistant ID to the Azure Assistants client. Demonstrates proper cleanup of manually created assistants. |
| [`azure_assistants_with_explicit_settings.py`](azure_assistants_with_explicit_settings.py) | Shows how to initialize an agent with a specific assistants client, configuring settings explicitly including endpoint and deployment name. |
| [`azure_assistants_with_function_tools.py`](azure_assistants_with_function_tools.py) | Demonstrates how to use function tools with agents. Shows both agent-level tools (defined when creating the agent) and query-level tools (provided with specific queries). |
| [`azure_assistants_with_session.py`](azure_assistants_with_session.py) | Demonstrates session management with Azure agents, including automatic session creation for stateless conversations and explicit session management for maintaining conversation context across multiple interactions. |
| [`azure_chat_client_basic.py`](azure_chat_client_basic.py) | The simplest way to create an agent using `Agent` with `AzureOpenAIChatClient`. Shows both streaming and non-streaming responses for chat-based interactions with Azure OpenAI models. |
| [`azure_chat_client_with_explicit_settings.py`](azure_chat_client_with_explicit_settings.py) | Shows how to initialize an agent with a specific chat client, configuring settings explicitly including endpoint and deployment name. |
| [`azure_chat_client_with_function_tools.py`](azure_chat_client_with_function_tools.py) | Demonstrates how to use function tools with agents. Shows both agent-level tools (defined when creating the agent) and query-level tools (provided with specific queries). |
| [`azure_chat_client_with_session.py`](azure_chat_client_with_session.py) | Demonstrates session management with Azure agents, including automatic session creation for stateless conversations and explicit session management for maintaining conversation context across multiple interactions. |
| [`azure_responses_client_basic.py`](azure_responses_client_basic.py) | The simplest way to create an agent using `Agent` with `AzureOpenAIResponsesClient`. Shows both streaming and non-streaming responses for structured response generation with Azure OpenAI models. |
| [`azure_responses_client_code_interpreter_files.py`](azure_responses_client_code_interpreter_files.py) | Demonstrates using `AzureOpenAIResponsesClient.get_code_interpreter_tool()` with file uploads for data analysis. Shows how to create, upload, and analyze CSV files using Python code execution with Azure OpenAI Responses. |
| [`azure_responses_client_image_analysis.py`](azure_responses_client_image_analysis.py) | Shows how to use Azure OpenAI Responses for image analysis and vision tasks. Demonstrates multi-modal messages combining text and image content using remote URLs. |
| [`azure_responses_client_with_code_interpreter.py`](azure_responses_client_with_code_interpreter.py) | Shows how to use `AzureOpenAIResponsesClient.get_code_interpreter_tool()` with Azure agents to write and execute Python code. Includes helper methods for accessing code interpreter data from response chunks. |
| [`azure_responses_client_with_explicit_settings.py`](azure_responses_client_with_explicit_settings.py) | Shows how to initialize an agent with a specific responses client, configuring settings explicitly including endpoint and deployment name. |
| [`azure_responses_client_with_file_search.py`](azure_responses_client_with_file_search.py) | Demonstrates using `AzureOpenAIResponsesClient.get_file_search_tool()` with Azure OpenAI Responses Client for direct document-based question answering and information retrieval from vector stores. |
| [`azure_responses_client_with_foundry.py`](azure_responses_client_with_foundry.py) | Shows how to create an agent using an Azure AI Foundry project endpoint instead of a direct Azure OpenAI endpoint. Requires the `azure-ai-projects` package. |
| [`azure_responses_client_with_function_tools.py`](azure_responses_client_with_function_tools.py) | Demonstrates how to use function tools with agents. Shows both agent-level tools (defined when creating the agent) and query-level tools (provided with specific queries). |
| [`azure_responses_client_with_hosted_mcp.py`](azure_responses_client_with_hosted_mcp.py) | Shows how to integrate Azure OpenAI Responses Client with hosted Model Context Protocol (MCP) servers using `AzureOpenAIResponsesClient.get_mcp_tool()` for extended functionality. |
| [`azure_responses_client_with_local_mcp.py`](azure_responses_client_with_local_mcp.py) | Shows how to integrate Azure OpenAI Responses Client with local Model Context Protocol (MCP) servers using MCPStreamableHTTPTool for extended functionality. |
| [`azure_responses_client_with_session.py`](azure_responses_client_with_session.py) | Demonstrates session management with Azure agents, including automatic session creation for stateless conversations and explicit session management for maintaining conversation context across multiple interactions. |

## Environment Variables

Make sure to set the following environment variables before running the examples:

- `AZURE_OPENAI_ENDPOINT`: Your Azure OpenAI endpoint
- `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME`: The name of your Azure OpenAI chat model deployment
- `AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME`: The name of your Azure OpenAI Responses deployment

For the Foundry project sample (`azure_responses_client_with_foundry.py`), also set:
- `AZURE_AI_PROJECT_ENDPOINT`: Your Azure AI Foundry project endpoint

Optionally, you can set:
- `AZURE_OPENAI_API_VERSION`: The API version to use (default is `2024-02-15-preview`)
- `AZURE_OPENAI_API_KEY`: Your Azure OpenAI API key (if not using `AzureCliCredential`)
- `AZURE_OPENAI_BASE_URL`: Your Azure OpenAI base URL (if different from the endpoint)

## Authentication

All examples use `AzureCliCredential` for authentication. Run `az login` in your terminal before running the examples, or replace `AzureCliCredential` with your preferred authentication method.

## Required role-based access control (RBAC) roles

To access the Azure OpenAI API, your Azure account or service principal needs one of the following RBAC roles assigned to the Azure OpenAI resource:

- **Cognitive Services OpenAI User**: Provides read access to Azure OpenAI resources and the ability to call the inference APIs. This is the minimum role required for running these examples.
- **Cognitive Services OpenAI Contributor**: Provides full access to Azure OpenAI resources, including the ability to create, update, and delete deployments and models.

For most scenarios, the **Cognitive Services OpenAI User** role is sufficient. You can assign this role through the Azure portal under the Azure OpenAI resource's "Access control (IAM)" section.

For more detailed information about Azure OpenAI RBAC roles, see: [Role-based access control for Azure OpenAI Service](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/role-based-access-control)
# Azure AI Agent Examples

This folder contains examples demonstrating different ways to create and use agents with the Azure AI client from the `agent_framework.azure` package. These examples use the `AzureAIClient` with the `azure-ai-projects` 2.x (V2) API surface (see [changelog](https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/ai/azure-ai-projects/CHANGELOG.md#200b1-2025-11-11)). For V1 (`azure-ai-agents` 1.x) samples using `AzureAIAgentClient`, see the [Azure AI V1 examples folder](../azure_ai_agent/). When using preview-only agent creation features on GA SDK versions, create `AIProjectClient` with `allow_preview=True`.

## Examples

| File | Description |
|------|-------------|
| [`azure_ai_basic.py`](azure_ai_basic.py) | The simplest way to create an agent using `AzureAIProjectAgentProvider`. Demonstrates both streaming and non-streaming responses with function tools. Shows automatic agent creation and basic weather functionality. |
| [`azure_ai_provider_methods.py`](azure_ai_provider_methods.py) | Comprehensive guide to `AzureAIProjectAgentProvider` methods: `create_agent()` for creating new agents, `get_agent()` for retrieving existing agents (by name, reference, or details), and `as_agent()` for wrapping SDK objects without HTTP calls. |
| [`azure_ai_use_latest_version.py`](azure_ai_use_latest_version.py) | Demonstrates how to reuse the latest version of an existing agent instead of creating a new agent version on each instantiation by using `provider.get_agent()` to retrieve the latest version. |
| [`azure_ai_with_agent_as_tool.py`](azure_ai_with_agent_as_tool.py) | Shows how to use the agent-as-tool pattern with Azure AI agents, where one agent delegates work to specialized sub-agents wrapped as tools using `as_tool()`. Demonstrates hierarchical agent architectures. |
| [`azure_ai_with_agent_to_agent.py`](azure_ai_with_agent_to_agent.py) | Shows how to use Agent-to-Agent (A2A) capabilities with Azure AI agents to enable communication with other agents using the A2A protocol. Requires an A2A connection configured in your Azure AI project. |
| [`azure_ai_with_azure_ai_search.py`](azure_ai_with_azure_ai_search.py) | Shows how to use Azure AI Search with Azure AI agents to search through indexed data and answer user questions with proper citations. Requires an Azure AI Search connection and index configured in your Azure AI project. |
| [`azure_ai_with_bing_grounding.py`](azure_ai_with_bing_grounding.py) | Shows how to use Bing Grounding search with Azure AI agents to search the web for current information and provide grounded responses with citations. Requires a Bing connection configured in your Azure AI project. |
| [`azure_ai_with_bing_custom_search.py`](azure_ai_with_bing_custom_search.py) | Shows how to use Bing Custom Search with Azure AI agents to search custom search instances and provide responses with relevant results. Requires a Bing Custom Search connection and instance configured in your Azure AI project. |
| [`azure_ai_with_browser_automation.py`](azure_ai_with_browser_automation.py) | Shows how to use Browser Automation with Azure AI agents to perform automated web browsing tasks and provide responses based on web interactions. Requires a Browser Automation connection configured in your Azure AI project. |
| [`azure_ai_with_code_interpreter.py`](azure_ai_with_code_interpreter.py) | Shows how to use `AzureAIClient.get_code_interpreter_tool()` with Azure AI agents to write and execute Python code for mathematical problem solving and data analysis. |
| [`azure_ai_with_code_interpreter_file_generation.py`](azure_ai_with_code_interpreter_file_generation.py) | Shows how to retrieve file IDs from code interpreter generated files using both streaming and non-streaming approaches. |
| [`azure_ai_with_code_interpreter_file_download.py`](azure_ai_with_code_interpreter_file_download.py) | Shows how to download files generated by code interpreter using the OpenAI containers API. |
| [`azure_ai_with_content_filtering.py`](azure_ai_with_content_filtering.py) | Shows how to enable content filtering (RAI policy) on Azure AI agents using `RaiConfig`. Requires creating an RAI policy in Azure AI Foundry portal first. |
| [`azure_ai_with_existing_agent.py`](azure_ai_with_existing_agent.py) | Shows how to work with a pre-existing agent by providing the agent name and version to the Azure AI client. Demonstrates agent reuse patterns for production scenarios. |
| [`azure_ai_with_existing_conversation.py`](azure_ai_with_existing_conversation.py) | Demonstrates how to use an existing conversation created on the service side with Azure AI agents. Shows two approaches: specifying conversation ID at the client level and using AgentSession with an existing conversation ID. |
| [`azure_ai_with_application_endpoint.py`](azure_ai_with_application_endpoint.py) | Demonstrates calling the Azure AI application-scoped endpoint. |
| [`azure_ai_with_explicit_settings.py`](azure_ai_with_explicit_settings.py) | Shows how to create an agent with explicitly configured `AzureAIClient` settings, including project endpoint, model deployment, and credentials rather than relying on environment variable defaults. |
| [`azure_ai_with_file_search.py`](azure_ai_with_file_search.py) | Shows how to use `AzureAIClient.get_file_search_tool()` with Azure AI agents to upload files, create vector stores, and enable agents to search through uploaded documents to answer user questions. |
| [`azure_ai_with_hosted_mcp.py`](azure_ai_with_hosted_mcp.py) | Shows how to integrate hosted Model Context Protocol (MCP) tools with Azure AI Agent using `AzureAIClient.get_mcp_tool()`. |
| [`azure_ai_with_local_mcp.py`](azure_ai_with_local_mcp.py) | Shows how to integrate local Model Context Protocol (MCP) tools with Azure AI agents. |
| [`azure_ai_with_response_format.py`](azure_ai_with_response_format.py) | Shows how to use structured outputs (response format) with Azure AI agents using Pydantic models to enforce specific response schemas. |
| [`azure_ai_with_runtime_json_schema.py`](azure_ai_with_runtime_json_schema.py) | Shows how to use structured outputs (response format) with Azure AI agents using a JSON schema to enforce specific response schemas. |
| [`azure_ai_with_search_context_agentic.py`](../../context_providers/azure_ai_search/azure_ai_with_search_context_agentic.py) | Shows how to use AzureAISearchContextProvider with agentic mode. Uses Knowledge Bases for multi-hop reasoning across documents with query planning. Recommended for most scenarios - slightly slower with more token consumption for query planning, but more accurate results. |
| [`azure_ai_with_search_context_semantic.py`](../../context_providers/azure_ai_search/azure_ai_with_search_context_semantic.py) | Shows how to use AzureAISearchContextProvider with semantic mode. Fast hybrid search with vector + keyword search and semantic ranking for RAG. Best for simple queries where speed is critical. |
| [`azure_ai_with_sharepoint.py`](azure_ai_with_sharepoint.py) | Shows how to use SharePoint grounding with Azure AI agents to search through SharePoint content and answer user questions with proper citations. Requires a SharePoint connection configured in your Azure AI project. |
| [`azure_ai_with_session.py`](azure_ai_with_session.py) | Demonstrates session management with Azure AI agents, including automatic session creation for stateless conversations and explicit session management for maintaining conversation context across multiple interactions. |
| [`azure_ai_with_image_generation.py`](azure_ai_with_image_generation.py) | Shows how to use `AzureAIClient.get_image_generation_tool()` with Azure AI agents to generate images based on text prompts. |
| [`azure_ai_with_memory_search.py`](azure_ai_with_memory_search.py) | Shows how to use memory search functionality with Azure AI agents for conversation persistence. Demonstrates creating memory stores and enabling agents to search through conversation history. |
| [`azure_ai_with_microsoft_fabric.py`](azure_ai_with_microsoft_fabric.py) | Shows how to use Microsoft Fabric with Azure AI agents to query Fabric data sources and provide responses based on data analysis. Requires a Microsoft Fabric connection configured in your Azure AI project. |
| [`azure_ai_with_openapi.py`](azure_ai_with_openapi.py) | Shows how to integrate OpenAPI specifications with Azure AI agents using dictionary-based tool configuration. Demonstrates using external REST APIs for dynamic data lookup. |
| [`azure_ai_with_reasoning.py`](azure_ai_with_reasoning.py) | Shows how to enable reasoning for a model that supports it. |
| [`azure_ai_with_web_search.py`](azure_ai_with_web_search.py) | Shows how to use `AzureAIClient.get_web_search_tool()` with Azure AI agents to perform web searches and retrieve up-to-date information from the internet. |

## Environment Variables

Before running the examples, you need to set up your environment variables. You can do this in one of two ways:

### Option 1: Using a .env file (Recommended)

1. Copy the `.env.example` file from the `python` directory to create a `.env` file:

   ```bash
   cp ../../../../.env.example ../../../../.env
   ```

2. Edit the `.env` file and add your values:

   ```env
   AZURE_AI_PROJECT_ENDPOINT="your-project-endpoint"
   AZURE_AI_MODEL_DEPLOYMENT_NAME="your-model-deployment-name"
   ```

### Option 2: Using environment variables directly

Set the environment variables in your shell:

```bash
export AZURE_AI_PROJECT_ENDPOINT="your-project-endpoint"
export AZURE_AI_MODEL_DEPLOYMENT_NAME="your-model-deployment-name"
```

### Required Variables

- `AZURE_AI_PROJECT_ENDPOINT`: Your Azure AI project endpoint (required for all examples)
- `AZURE_AI_MODEL_DEPLOYMENT_NAME`: The name of your model deployment (required for all examples)

## Authentication

All examples use `AzureCliCredential` for authentication by default. Before running the examples:

1. Install the Azure CLI
2. Run `az login` to authenticate with your Azure account
3. Ensure you have appropriate permissions to the Azure AI project

Alternatively, you can replace `AzureCliCredential` with other authentication options like `DefaultAzureCredential` or environment-based credentials.

## Running the Examples

Each example can be run independently. Navigate to this directory and run any example:

```bash
python azure_ai_basic.py
python azure_ai_with_code_interpreter.py
# ... etc
```

The examples demonstrate various patterns for working with Azure AI agents, from basic usage to advanced scenarios like session management and structured outputs.
# Azure AI Agent Examples

This folder contains examples demonstrating different ways to create and use agents with Azure AI using the `AzureAIAgentsProvider` from the `agent_framework.azure` package. These examples use the `azure-ai-agents` 1.x (V1) API surface. For updated V2 (`azure-ai-projects` 2.x) samples, see the [Azure AI V2 examples folder](../azure_ai/).

## Provider Pattern

All examples in this folder use the `AzureAIAgentsProvider` class which provides a high-level interface for agent operations:

- **`create_agent()`** - Create a new agent on the Azure AI service
- **`get_agent()`** - Retrieve an existing agent by ID or from a pre-fetched Agent object
- **`as_agent()`** - Wrap an SDK Agent object as a Agent without HTTP calls

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
| [`azure_ai_with_bing_custom_search.py`](azure_ai_with_bing_custom_search.py) | Shows how to use Bing Custom Search with Azure AI agents to find real-time information from the web using custom search configurations. Demonstrates how to use `AzureAIAgentClient.get_web_search_tool()` with custom search instances. |
| [`azure_ai_with_bing_grounding.py`](azure_ai_with_bing_grounding.py) | Shows how to use Bing Grounding search with Azure AI agents to find real-time information from the web. Demonstrates `AzureAIAgentClient.get_web_search_tool()` with proper source citations and comprehensive error handling. |
| [`azure_ai_with_bing_grounding_citations.py`](azure_ai_with_bing_grounding_citations.py) | Demonstrates how to extract and display citations from Bing Grounding search responses. Shows how to collect citation annotations (title, URL, snippet) during streaming responses, enabling users to verify sources and access referenced content. |
| [`azure_ai_with_code_interpreter_file_generation.py`](azure_ai_with_code_interpreter_file_generation.py) | Shows how to retrieve file IDs from code interpreter generated files using both streaming and non-streaming approaches. |
| [`azure_ai_with_code_interpreter.py`](azure_ai_with_code_interpreter.py) | Shows how to use `AzureAIAgentClient.get_code_interpreter_tool()` with Azure AI agents to write and execute Python code. Includes helper methods for accessing code interpreter data from response chunks. |
| [`azure_ai_with_existing_agent.py`](azure_ai_with_existing_agent.py) | Shows how to work with an existing SDK Agent object using `provider.as_agent()`. This wraps the agent without making HTTP calls. |
| [`azure_ai_with_existing_session.py`](azure_ai_with_existing_session.py) | Shows how to work with a pre-existing session by providing the session ID. Demonstrates proper cleanup of manually created sessions. |
| [`azure_ai_with_explicit_settings.py`](azure_ai_with_explicit_settings.py) | Shows how to create an agent with explicitly configured provider settings, including project endpoint and model deployment name. |
| [`azure_ai_with_azure_ai_search.py`](azure_ai_with_azure_ai_search.py) | Demonstrates how to use Azure AI Search with Azure AI agents. Shows how to create an agent with search tools using the SDK directly and wrap it with `provider.get_agent()`. |
| [`azure_ai_with_file_search.py`](azure_ai_with_file_search.py) | Demonstrates how to use `AzureAIAgentClient.get_file_search_tool()` with Azure AI agents to search through uploaded documents. Shows file upload, vector store creation, and querying document content. |
| [`azure_ai_with_function_tools.py`](azure_ai_with_function_tools.py) | Demonstrates how to use function tools with agents. Shows both agent-level tools (defined when creating the agent) and query-level tools (provided with specific queries). |
| [`azure_ai_with_hosted_mcp.py`](azure_ai_with_hosted_mcp.py) | Shows how to use `AzureAIAgentClient.get_mcp_tool()` with hosted Model Context Protocol (MCP) servers for enhanced functionality and tool integration. Demonstrates remote MCP server connections and tool discovery. |
| [`azure_ai_with_local_mcp.py`](azure_ai_with_local_mcp.py) | Shows how to integrate Azure AI agents with local Model Context Protocol (MCP) servers for enhanced functionality and tool integration. Demonstrates both agent-level and run-level tool configuration. |
| [`azure_ai_with_multiple_tools.py`](azure_ai_with_multiple_tools.py) | Demonstrates how to use multiple tools together with Azure AI agents, including web search, MCP servers, and function tools using client static methods. Shows coordinated multi-tool interactions and approval workflows. |
| [`azure_ai_with_openapi_tools.py`](azure_ai_with_openapi_tools.py) | Demonstrates how to use OpenAPI tools with Azure AI agents to integrate external REST APIs. Shows OpenAPI specification loading, anonymous authentication, session context management, and coordinated multi-API conversations. |
| [`azure_ai_with_response_format.py`](azure_ai_with_response_format.py) | Demonstrates how to use structured outputs with Azure AI agents using Pydantic models. |
| [`azure_ai_with_session.py`](azure_ai_with_session.py) | Demonstrates session management with Azure AI agents, including automatic session creation for stateless conversations and explicit session management for maintaining conversation context across multiple interactions. |

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
