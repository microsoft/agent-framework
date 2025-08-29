# Azure Chat Agent Examples

This folder contains examples demonstrating different ways to create and use agents with the Azure Chat client from the `agent_framework.azure` package.

## Examples

| File | Description |
|------|-------------|
| [`azure_chat_client_basic.py`](azure_chat_client_basic.py) | The simplest way to create an agent using `ChatClientAgent` with `AzureChatClient`. Shows both streaming and non-streaming responses for chat-based interactions with Azure OpenAI models. |
| [`azure_chat_client_with_function_tools.py`](azure_chat_client_with_function_tools.py) | Demonstrates how to use function tools with agents. Shows both agent-level tools (defined when creating the agent) and query-level tools (provided with specific queries). |
| [`azure_chat_client_with_thread.py`](azure_chat_client_with_thread.py) | Demonstrates thread management with Azure agents, including automatic thread creation for stateless conversations and explicit thread management for maintaining conversation context across multiple interactions. |

## Environment Variables

Make sure to set the following environment variables before running the examples:

- `AZURE_OPENAI_ENDPOINT`: Your Azure OpenAI endpoint
- `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME`: The name of your Azure OpenAI deployment

## Authentication

All examples use `AzureCliCredential` for authentication. Run `az login` in your terminal before running the examples, or replace `AzureCliCredential` with your preferred authentication method.
