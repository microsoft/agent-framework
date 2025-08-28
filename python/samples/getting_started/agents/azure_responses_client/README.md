# Azure Responses Agent Examples

This folder contains examples demonstrating different ways to create and use agents with the Azure Responses client from the `agent_framework.azure` package.

## Examples

| File | Description |
|------|-------------|
| [`azure_responses_client_basic.py`](azure_responses_client_basic.py) | The simplest way to create an agent using `ChatClientAgent` with `AzureResponsesClient`. Shows both streaming and non-streaming responses for structured response generation with Azure OpenAI models. |
| [`azure_responses_client_with_function_tools.py`](azure_responses_client_with_function_tools.py) | Demonstrates how to use function tools with agents. Shows both agent-level tools (defined when creating the agent) and query-level tools (provided with specific queries). |
| [`azure_responses_client_with_code_interpreter.py`](azure_responses_client_with_code_interpreter.py) | Shows how to use the HostedCodeInterpreterTool with Azure agents to write and execute Python code. Includes helper methods for accessing code interpreter data from response chunks. |
| [`azure_responses_client_with_thread.py`](azure_responses_client_with_thread.py) | Demonstrates thread management with Azure agents, including automatic thread creation for stateless conversations and explicit thread management for maintaining conversation context across multiple interactions. |

## Environment Variables

Make sure to set the following environment variables before running the examples:

- `AZURE_OPENAI_ENDPOINT`: Your Azure OpenAI endpoint
- `AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME`: The name of your Azure OpenAI deployment

## Authentication

All examples use `AzureCliCredential` for authentication. Run `az login` in your terminal before running the examples, or replace `AzureCliCredential` with your preferred authentication method.
