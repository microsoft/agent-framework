# Foundry Agent Examples

This folder contains examples demonstrating different ways to create and use agents with the Foundry chat client from the `agent_framework.foundry` package.

## Examples

| File | Description |
|------|-------------|
| [`foundry_basic.py`](foundry_basic.py) | The simplest way to create an agent using `ChatAgent` with `FoundryChatClient`. It automatically handles all configuration using environment variables. |
| [`foundry_with_explicit_settings.py`](foundry_with_explicit_settings.py) | Shows how to create an agent with explicitly configured `FoundryChatClient` settings, including project endpoint, model deployment, credentials, and agent name. |
| [`foundry_with_existing_agent.py`](foundry_with_existing_agent.py) | Shows how to work with a pre-existing agent by providing the agent ID to the Foundry chat client. This example also demonstrates proper cleanup of manually created agents. |
| [`foundry_with_function_tools.py`](foundry_with_function_tools.py) | Demonstrates how to use function tools with agents. Shows both agent-level tools (defined when creating the agent) and query-level tools (provided with specific queries). |
| [`foundry_with_code_interpreter.py`](foundry_with_code_interpreter.py) | Shows how to use the HostedCodeInterpreterTool with Foundry agents to write and execute Python code. Includes helper methods for accessing code interpreter data from response chunks. |
| [`foundry_with_thread.py`](foundry_with_thread.py) | Demonstrates thread management with Foundry agents, including automatic thread creation for stateless conversations and explicit thread management for maintaining conversation context across multiple interactions. |

## Environment Variables

Make sure to set the following environment variables before running the examples:

- `FOUNDRY_PROJECT_ENDPOINT`: Your Azure AI Foundry project endpoint
- `FOUNDRY_MODEL_DEPLOYMENT_NAME`: The name of your model deployment
