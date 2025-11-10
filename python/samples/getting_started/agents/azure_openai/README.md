# Azure OpenAI Agent Examples

This folder contains examples demonstrating different ways to create and use agents with the different Azure OpenAI chat client from the `agent_framework.azure` package.

## Examples

| File | Description |
|------|-------------|
| [`azure_assistants_basic.py`](azure_assistants_basic.py) | The simplest way to create an agent using `ChatAgent` with `AzureOpenAIAssistantsClient`. Shows both streaming and non-streaming responses with automatic assistant creation and cleanup. |
| [`azure_assistants_with_code_interpreter.py`](azure_assistants_with_code_interpreter.py) | Shows how to use the HostedCodeInterpreterTool with Azure agents to write and execute Python code. Includes helper methods for accessing code interpreter data from response chunks. |
| [`azure_assistants_with_existing_assistant.py`](azure_assistants_with_existing_assistant.py) | Shows how to work with a pre-existing assistant by providing the assistant ID to the Azure Assistants client. Demonstrates proper cleanup of manually created assistants. |
| [`azure_assistants_with_explicit_settings.py`](azure_assistants_with_explicit_settings.py) | Shows how to initialize an agent with a specific assistants client, configuring settings explicitly including endpoint and deployment name. |
| [`azure_assistants_with_function_tools.py`](azure_assistants_with_function_tools.py) | Demonstrates how to use function tools with agents. Shows both agent-level tools (defined when creating the agent) and query-level tools (provided with specific queries). |
| [`azure_assistants_with_thread.py`](azure_assistants_with_thread.py) | Demonstrates thread management with Azure agents, including automatic thread creation for stateless conversations and explicit thread management for maintaining conversation context across multiple interactions. |
| [`azure_chat_client_basic.py`](azure_chat_client_basic.py) | The simplest way to create an agent using `ChatAgent` with `AzureOpenAIChatClient`. Shows both streaming and non-streaming responses for chat-based interactions with Azure OpenAI models. |
| [`azure_chat_client_with_explicit_settings.py`](azure_chat_client_with_explicit_settings.py) | Shows how to initialize an agent with a specific chat client, configuring settings explicitly including endpoint and deployment name. |
| [`azure_chat_client_with_function_tools.py`](azure_chat_client_with_function_tools.py) | Demonstrates how to use function tools with agents. Shows both agent-level tools (defined when creating the agent) and query-level tools (provided with specific queries). |
| [`azure_chat_client_with_thread.py`](azure_chat_client_with_thread.py) | Demonstrates thread management with Azure agents, including automatic thread creation for stateless conversations and explicit thread management for maintaining conversation context across multiple interactions. |
| [`azure_responses_client_basic.py`](azure_responses_client_basic.py) | The simplest way to create an agent using `ChatAgent` with `AzureOpenAIResponsesClient`. Shows both streaming and non-streaming responses for structured response generation with Azure OpenAI models. |
| [`azure_responses_client_code_interpreter_files.py`](azure_responses_client_code_interpreter_files.py) | Demonstrates using HostedCodeInterpreterTool with file uploads for data analysis. Shows how to create, upload, and analyze CSV files using Python code execution with Azure OpenAI Responses. |
| [`azure_responses_client_image_analysis.py`](azure_responses_client_image_analysis.py) | Shows how to use Azure OpenAI Responses for image analysis and vision tasks. Demonstrates multi-modal messages combining text and image content using remote URLs. |
| [`azure_responses_client_with_code_interpreter.py`](azure_responses_client_with_code_interpreter.py) | Shows how to use the HostedCodeInterpreterTool with Azure agents to write and execute Python code. Includes helper methods for accessing code interpreter data from response chunks. |
| [`azure_responses_client_with_explicit_settings.py`](azure_responses_client_with_explicit_settings.py) | Shows how to initialize an agent with a specific responses client, configuring settings explicitly including endpoint and deployment name. |
| [`azure_responses_client_with_function_tools.py`](azure_responses_client_with_function_tools.py) | Demonstrates how to use function tools with agents. Shows both agent-level tools (defined when creating the agent) and query-level tools (provided with specific queries). |
| [`azure_responses_client_with_local_mcp.py`](azure_responses_client_with_local_mcp.py) | Shows how to integrate Azure OpenAI Responses Client with local Model Context Protocol (MCP) servers using MCPStreamableHTTPTool for extended functionality. |
| [`azure_responses_client_with_thread.py`](azure_responses_client_with_thread.py) | Demonstrates thread management with Azure agents, including automatic thread creation for stateless conversations and explicit thread management for maintaining conversation context across multiple interactions. |

## Environment Variables

Make sure to set the following environment variables before running the examples:

- `AZURE_OPENAI_ENDPOINT`: Your Azure OpenAI endpoint
- `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME`: The name of your Azure OpenAI chat model deployment
- `AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME`: The name of your Azure OpenAI Responses deployment

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
