# Azure AI Agent Examples

This folder contains examples demonstrating different ways to create and use agents with the Azure AI client from the `agent_framework.azure` package.

## Examples

| File | Description |
|------|-------------|
| [`azure_ai_basic.py`](azure_ai_basic.py) | The simplest way to create an agent using `AzureAIClient`. Demonstrates both streaming and non-streaming responses with function tools. Shows automatic agent creation and basic weather functionality. |
| [`azure_ai_use_latest_version.py`](azure_ai_use_latest_version.py) | Demonstrates how to reuse the latest version of an existing agent instead of creating a new agent version on each instantiation using the `use_latest_version=True` parameter. |
| [`azure_ai_with_azure_ai_search.py`](azure_ai_with_azure_ai_search.py) | Shows how to use Azure AI Search with Azure AI agents to search through indexed data and answer user questions with proper citations. Requires an Azure AI Search connection and index configured in your Azure AI project. |
| [`azure_ai_with_code_interpreter.py`](azure_ai_with_code_interpreter.py) | Shows how to use the `HostedCodeInterpreterTool` with Azure AI agents to write and execute Python code for mathematical problem solving and data analysis. |
| [`azure_ai_with_existing_agent.py`](azure_ai_with_existing_agent.py) | Shows how to work with a pre-existing agent by providing the agent name and version to the Azure AI client. Demonstrates agent reuse patterns for production scenarios. |
| [`azure_ai_with_existing_conversation.py`](azure_ai_with_existing_conversation.py) | Demonstrates how to use an existing conversation created on the service side with Azure AI agents. Shows two approaches: specifying conversation ID at the client level and using AgentThread with an existing conversation ID. |
| [`azure_ai_with_explicit_settings.py`](azure_ai_with_explicit_settings.py) | Shows how to create an agent with explicitly configured `AzureAIClient` settings, including project endpoint, model deployment, and credentials rather than relying on environment variable defaults. |
| [`azure_ai_with_file_search.py`](azure_ai_with_file_search.py) | Shows how to use the `HostedFileSearchTool` with Azure AI agents to upload files, create vector stores, and enable agents to search through uploaded documents to answer user questions. |
| [`azure_ai_with_hosted_mcp.py`](azure_ai_with_hosted_mcp.py) | Shows how to integrate hosted Model Context Protocol (MCP) tools with Azure AI Agent. |
| [`azure_ai_with_response_format.py`](azure_ai_with_response_format.py) | Shows how to use structured outputs (response format) with Azure AI agents using Pydantic models to enforce specific response schemas. |
| [`azure_ai_with_thread.py`](azure_ai_with_thread.py) | Demonstrates thread management with Azure AI agents, including automatic thread creation for stateless conversations and explicit thread management for maintaining conversation context across multiple interactions. |
| [`azure_ai_with_image_generation.py`](azure_ai_with_image_generation.py) | Shows how to use the `ImageGenTool` with Azure AI agents to generate images based on text prompts. |
| [`azure_ai_with_web_search.py`](azure_ai_with_web_search.py) | Shows how to use the `HostedWebSearchTool` with Azure AI agents to perform web searches and retrieve up-to-date information from the internet. |

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

The examples demonstrate various patterns for working with Azure AI agents, from basic usage to advanced scenarios like thread management and structured outputs.
