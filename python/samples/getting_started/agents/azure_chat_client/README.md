# Azure Chat Agent Examples

This folder contains examples demonstrating different ways to create and use agents with the Azure Chat client from the `agent_framework.azure` package.

## Examples

| File | Description |
|------|-------------|
| [`azure_chat_client_basic.py`](azure_chat_client_basic.py) | The simplest way to create an agent using `ChatAgent` with `AzureChatClient`. Shows both streaming and non-streaming responses for chat-based interactions with Azure OpenAI models. |
| [`azure_chat_client_with_explicit_settings.py`](azure_chat_client_with_explicit_settings.py) | Shows how to initialize an agent with a specific chat client, configuring settings explicitly including endpoint and deployment name. |
| [`azure_chat_client_with_function_tools.py`](azure_chat_client_with_function_tools.py) | Demonstrates how to use function tools with agents. Shows both agent-level tools (defined when creating the agent) and query-level tools (provided with specific queries). |
| [`azure_chat_client_with_thread.py`](azure_chat_client_with_thread.py) | Demonstrates thread management with Azure agents, including automatic thread creation for stateless conversations and explicit thread management for maintaining conversation context across multiple interactions. |

## Environment Variables

Make sure to set the following environment variables before running the examples:

- `AZURE_OPENAI_ENDPOINT`: Your Azure OpenAI endpoint
- `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME`: The name of your Azure OpenAI deployment

## Authentication

All examples use `AzureCliCredential` for authentication. Run `az login` in your terminal before running the examples, or replace `AzureCliCredential` with your preferred authentication method.

## Required role-based access control (RBAC) roles

To access the Azure OpenAI API, your Azure account or service principal needs one of the following RBAC roles assigned to the Azure OpenAI resource:

- **Cognitive Services OpenAI User**: Provides read access to Azure OpenAI resources and the ability to call the inference APIs. This is the minimum role required for running these examples.
- **Cognitive Services OpenAI Contributor**: Provides full access to Azure OpenAI resources, including the ability to create, update, and delete deployments and models.

For most scenarios, the **Cognitive Services OpenAI User** role is sufficient. You can assign this role through the Azure portal under the Azure OpenAI resource's "Access control (IAM)" section.

For more detailed information about Azure OpenAI RBAC roles, see: [Role-based access control for Azure OpenAI Service](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/role-based-access-control)
