# OpenAI Assistants Agent Examples

This folder contains examples demonstrating different ways to create and use agents with the OpenAI Assistants client from the `agent_framework.openai` package.

## Examples

| File | Description |
|------|-------------|
| [`openai_assistants_basic.py`](openai_assistants_basic.py) | The simplest way to create an agent using `ChatAgent` with `OpenAIAssistantsClient`. Shows both streaming and non-streaming responses with automatic assistant creation and cleanup. |
| [`openai_assistants_with_existing_assistant.py`](openai_assistants_with_existing_assistant.py) | Shows how to work with a pre-existing assistant by providing the assistant ID to the OpenAI Assistants client. Demonstrates proper cleanup of manually created assistants. |
| [`openai_assistants_with_explicit_settings.py`](openai_assistants_with_explicit_settings.py) | Shows how to initialize an agent with a specific assistants client, configuring settings explicitly including API key and model ID. |
| [`openai_assistants_with_function_tools.py`](openai_assistants_with_function_tools.py) | Demonstrates how to use function tools with agents. Shows both agent-level tools (defined when creating the agent) and query-level tools (provided with specific queries). |
| [`openai_assistants_with_code_interpreter.py`](openai_assistants_with_code_interpreter.py) | Shows how to use the HostedCodeInterpreterTool with OpenAI agents to write and execute Python code. Includes helper methods for accessing code interpreter data from response chunks. |
| [`openai_assistants_with_file_search.py`](openai_assistants_with_file_search.py) | Demonstrates how to use file search capabilities with OpenAI agents, allowing the agent to search through uploaded files to answer questions. |
| [`openai_assistants_with_thread.py`](openai_assistants_with_thread.py) | Demonstrates thread management with OpenAI agents, including automatic thread creation for stateless conversations and explicit thread management for maintaining conversation context across multiple interactions. |

## Environment Variables

Make sure to set the following environment variables before running the examples:

- `OPENAI_API_KEY`: Your OpenAI API key
- `OPENAI_CHAT_MODEL_ID`: The OpenAI model to use (e.g., `gpt-4o`, `gpt-4o-mini`, `gpt-3.5-turbo`)
