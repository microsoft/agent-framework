# Azure Responses Agent Examples

This folder contains examples demonstrating different ways to create and use agents with the Azure Responses client from the `agent_framework.azure` package.

## Examples

| File | Description |
|------|-------------|
| [`azure_responses_client_basic.py`](azure_responses_client_basic.py) | The simplest way to create an agent using `ChatAgent` with `AzureResponsesClient`. Shows both streaming and non-streaming responses for structured response generation with Azure OpenAI models. |
| [`azure_responses_client_with_explicit_settings.py`](azure_responses_client_with_explicit_settings.py) | Shows how to initialize an agent with a specific responses client, configuring settings explicitly including endpoint and deployment name. |
| [`azure_responses_client_with_function_tools.py`](azure_responses_client_with_function_tools.py) | Demonstrates how to use function tools with agents. Shows both agent-level tools (defined when creating the agent) and query-level tools (provided with specific queries). |
| [`azure_responses_client_with_code_interpreter.py`](azure_responses_client_with_code_interpreter.py) | Shows how to use the HostedCodeInterpreterTool with Azure agents to write and execute Python code. Includes helper methods for accessing code interpreter data from response chunks. |
| [`azure_responses_client_with_thread.py`](azure_responses_client_with_thread.py) | Demonstrates thread management with Azure agents, including automatic thread creation for stateless conversations and explicit thread management for maintaining conversation context across multiple interactions. |

## Environment Variables

Make sure to set the following environment variables before running the examples:

- `AZURE_OPENAI_ENDPOINT`: Your Azure OpenAI endpoint
- `AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME`: The name of your Azure OpenAI deployment

## Authentication

All examples use `AzureCliCredential` for authentication. Run `az login` in your terminal before running the examples, or replace `AzureCliCredential` with your preferred authentication method.

## Required role-based access control (RBAC) roles

To access the Azure OpenAI API, your Azure account or service principal needs one of the following RBAC roles assigned to the Azure OpenAI resource:

- **Cognitive Services OpenAI User**: Provides read access to Azure OpenAI resources and the ability to call the inference APIs. This is the minimum role required for running these examples.
- **Cognitive Services OpenAI Contributor**: Provides full access to Azure OpenAI resources, including the ability to create, update, and delete deployments and models.

For most scenarios, the **Cognitive Services OpenAI User** role is sufficient. You can assign this role through the Azure portal under the Azure OpenAI resource's "Access control (IAM)" section.

For more detailed information about Azure OpenAI RBAC roles, see: [Role-based access control for Azure OpenAI Service](https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/role-based-access-control)
