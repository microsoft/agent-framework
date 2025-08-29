# OpenAI Chat Agent Examples

This folder contains examples demonstrating different ways to create and use agents with the OpenAI Chat client from the `agent_framework.openai` package.

## Examples

| File | Description |
|------|-------------|
| [`openai_chat_client_basic.py`](openai_chat_client_basic.py) | The simplest way to create an agent using `ChatClientAgent` with `OpenAIChatClient`. Shows both streaming and non-streaming responses for chat-based interactions with OpenAI models. |
| [`openai_chat_client_with_function_tools.py`](openai_chat_client_with_function_tools.py) | Demonstrates how to use function tools with agents. Shows both agent-level tools (defined when creating the agent) and query-level tools (provided with specific queries). |
| [`openai_chat_client_with_local_mcp.py`](openai_chat_client_with_local_mcp.py) | Shows how to integrate OpenAI agents with local Model Context Protocol (MCP) servers for enhanced functionality and tool integration. |
| [`openai_chat_client_with_thread.py`](openai_chat_client_with_thread.py) | Demonstrates thread management with OpenAI agents, including automatic thread creation for stateless conversations and explicit thread management for maintaining conversation context across multiple interactions. |
| [`openai_chat_client_with_web_search.py`](openai_chat_client_with_web_search.py) | Shows how to use web search capabilities with OpenAI agents to retrieve and use information from the internet in responses. |

## Environment Variables

Make sure to set the following environment variables before running the examples:

- `OPENAI_API_KEY`: Your OpenAI API key
- `OPENAI_CHAT_MODEL_ID`: The OpenAI model to use (e.g., `gpt-4o`, `gpt-4o-mini`, `gpt-3.5-turbo`)
