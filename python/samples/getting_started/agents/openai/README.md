# OpenAI Agent Framework Examples

This folder contains examples demonstrating different ways to create and use agents with the OpenAI Assistants client from the `agent_framework.openai` package.

## Examples

| File | Description |
|------|-------------|
| [`openai_assistants_basic.py`](openai_assistants_basic.py) | The simplest way to create an agent using `ChatAgent` with `OpenAIAssistantsClient`. Shows both streaming and non-streaming responses with automatic assistant creation and cleanup. |
| [`openai_assistants_with_code_interpreter.py`](openai_assistants_with_code_interpreter.py) | Shows how to use the HostedCodeInterpreterTool with OpenAI agents to write and execute Python code. Includes helper methods for accessing code interpreter data from response chunks. |
| [`openai_assistants_with_existing_assistant.py`](openai_assistants_with_existing_assistant.py) | Shows how to work with a pre-existing assistant by providing the assistant ID to the OpenAI Assistants client. Demonstrates proper cleanup of manually created assistants. |
| [`openai_assistants_with_explicit_settings.py`](openai_assistants_with_explicit_settings.py) | Shows how to initialize an agent with a specific assistants client, configuring settings explicitly including API key and model ID. |
| [`openai_assistants_with_file_search.py`](openai_assistants_with_file_search.py) | Demonstrates how to use file search capabilities with OpenAI agents, allowing the agent to search through uploaded files to answer questions. |
| [`openai_assistants_with_function_tools.py`](openai_assistants_with_function_tools.py) | Demonstrates how to use function tools with agents. Shows both agent-level tools (defined when creating the agent) and query-level tools (provided with specific queries). |
| [`openai_assistants_with_thread.py`](openai_assistants_with_thread.py) | Demonstrates thread management with OpenAI agents, including automatic thread creation for stateless conversations and explicit thread management for maintaining conversation context across multiple interactions. |
| [`openai_chat_client_basic.py`](openai_chat_client_basic.py) | The simplest way to create an agent using `ChatAgent` with `OpenAIChatClient`. Shows both streaming and non-streaming responses for chat-based interactions with OpenAI models. |
| [`openai_chat_client_with_explicit_settings.py`](openai_chat_client_with_explicit_settings.py) | Shows how to initialize an agent with a specific chat client, configuring settings explicitly including API key and model ID. |
| [`openai_chat_client_with_function_tools.py`](openai_chat_client_with_function_tools.py) | Demonstrates how to use function tools with agents. Shows both agent-level tools (defined when creating the agent) and query-level tools (provided with specific queries). |
| [`openai_chat_client_with_local_mcp.py`](openai_chat_client_with_local_mcp.py) | Shows how to integrate OpenAI agents with local Model Context Protocol (MCP) servers for enhanced functionality and tool integration. |
| [`openai_chat_client_with_thread.py`](openai_chat_client_with_thread.py) | Demonstrates thread management with OpenAI agents, including automatic thread creation for stateless conversations and explicit thread management for maintaining conversation context across multiple interactions. |
| [`openai_chat_client_with_web_search.py`](openai_chat_client_with_web_search.py) | Shows how to use web search capabilities with OpenAI agents to retrieve and use information from the internet in responses. |
| [`openai_responses_client_basic.py`](openai_responses_client_basic.py) | The simplest way to create an agent using `ChatAgent` with `OpenAIResponsesClient`. Shows both streaming and non-streaming responses for structured response generation with OpenAI models. |
| [`openai_responses_client_image_analysis.py`](openai_responses_client_image_analysis.py) | Demonstrates how to use vision capabilities with agents to analyze images. |
| [`openai_responses_client_image_generation.py`](openai_responses_client_image_generation.py) | Demonstrates how to use image generation capabilities with OpenAI agents to create images based on text descriptions. Requires PIL (Pillow) for image display. |
| [`openai_responses_client_reasoning.py`](openai_responses_client_reasoning.py) | Demonstrates how to use reasoning capabilities with OpenAI agents, showing how the agent can provide detailed reasoning for its responses. |
| [`openai_responses_client_streaming_image_generation.py`](openai_responses_client_streaming_image_generation.py) | Demonstrates streaming image generation with partial images for real-time image creation feedback and improved user experience. |
| [`openai_responses_client_with_code_interpreter.py`](openai_responses_client_with_code_interpreter.py) | Shows how to use the HostedCodeInterpreterTool with OpenAI agents to write and execute Python code. Includes helper methods for accessing code interpreter data from response chunks. |
| [`openai_responses_client_with_explicit_settings.py`](openai_responses_client_with_explicit_settings.py) | Shows how to initialize an agent with a specific responses client, configuring settings explicitly including API key and model ID. |
| [`openai_responses_client_with_file_search.py`](openai_responses_client_with_file_search.py) | Demonstrates how to use file search capabilities with OpenAI agents, allowing the agent to search through uploaded files to answer questions. |
| [`openai_responses_client_with_function_tools.py`](openai_responses_client_with_function_tools.py) | Demonstrates how to use function tools with agents. Shows both agent-level tools (defined when creating the agent) and run-level tools (provided with specific queries). |
| [`openai_responses_client_with_hosted_mcp.py`](openai_responses_client_with_hosted_mcp.py) | Shows how to integrate OpenAI agents with hosted Model Context Protocol (MCP) servers, including approval workflows and tool management for remote MCP services. |
| [`openai_responses_client_with_local_mcp.py`](openai_responses_client_with_local_mcp.py) | Shows how to integrate OpenAI agents with local Model Context Protocol (MCP) servers for enhanced functionality and tool integration. |
| [`openai_responses_client_with_structured_output.py`](openai_responses_client_with_structured_output.py) | Demonstrates how to use structured outputs with OpenAI agents to get structured data responses in predefined formats. |
| [`openai_responses_client_with_thread.py`](openai_responses_client_with_thread.py) | Demonstrates thread management with OpenAI agents, including automatic thread creation for stateless conversations and explicit thread management for maintaining conversation context across multiple interactions. |
| [`openai_responses_client_with_web_search.py`](openai_responses_client_with_web_search.py) | Shows how to use web search capabilities with OpenAI agents to retrieve and use information from the internet in responses. |

## Environment Variables

Make sure to set the following environment variables before running the examples:

- `OPENAI_API_KEY`: Your OpenAI API key
- `OPENAI_CHAT_MODEL_ID`: The OpenAI model to use (e.g., `gpt-4o`, `gpt-4o-mini`, `gpt-3.5-turbo`)
- `OPENAI_RESPONSES_MODEL_ID`: The OpenAI model to use (e.g., `gpt-4o`, `gpt-4o-mini`, `gpt-3.5-turbo`)
- For image processing examples, use a vision-capable model like `gpt-4o` or `gpt-4o-mini`

Optionally, you can set:
- `OPENAI_ORG_ID`: Your OpenAI organization ID (if applicable)
- `OPENAI_API_BASE_URL`: Your OpenAI base URL (if using a different base URL)

## Optional Dependencies

Some examples require additional dependencies:

- **Image Generation Example**: The `openai_responses_client_image_generation.py` example requires PIL (Pillow) for image display. Install with:
  ```bash
  # Using uv
  uv add pillow

  # Or using pip
  pip install pillow
  ```
