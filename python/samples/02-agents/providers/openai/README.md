# OpenAI Provider Samples

This folder contains OpenAI provider samples for the generic clients in
`agent_framework.openai`.

## Chat Completions API samples (`OpenAIChatCompletionClient`)

| File | Description |
|------|-------------|
| [`chat_completion_client_basic.py`](chat_completion_client_basic.py) | Basic non-streaming and streaming chat completion sample with an explicit `gpt-5.4-nano` model and API key. |
| [`chat_completion_client_with_explicit_settings.py`](chat_completion_client_with_explicit_settings.py) | Chat completion sample with explicit model and API key settings. |
| [`chat_completion_client_with_function_tools.py`](chat_completion_client_with_function_tools.py) | Function tools with agent-level and run-level patterns. |
| [`chat_completion_client_with_local_mcp.py`](chat_completion_client_with_local_mcp.py) | Local MCP integration with the chat completions client. |
| [`chat_completion_client_with_runtime_json_schema.py`](chat_completion_client_with_runtime_json_schema.py) | Runtime JSON schema output with the chat completions client. |
| [`chat_completion_client_with_session.py`](chat_completion_client_with_session.py) | Session management with the chat completions client. |
| [`chat_completion_client_with_web_search.py`](chat_completion_client_with_web_search.py) | Web search with the chat completions client. |

## Responses API samples (`OpenAIChatClient`)

| File | Description |
|------|-------------|
| [`client_basic.py`](client_basic.py) | Basic non-streaming and streaming responses sample with an explicit `gpt-5.4-nano` model and API key. |
| [`client_image_analysis.py`](client_image_analysis.py) | Analyze images with the responses client. |
| [`client_image_generation.py`](client_image_generation.py) | Generate images from text prompts. |
| [`client_reasoning.py`](client_reasoning.py) | Reasoning-focused sample for models such as `gpt-5`. |
| [`client_streaming_image_generation.py`](client_streaming_image_generation.py) | Streaming image generation sample. |
| [`client_with_agent_as_tool.py`](client_with_agent_as_tool.py) | Agent-as-tool orchestration pattern. |
| [`client_with_code_interpreter.py`](client_with_code_interpreter.py) | Code interpreter sample. |
| [`client_with_code_interpreter_files.py`](client_with_code_interpreter_files.py) | Code interpreter sample with uploaded files. |
| [`client_with_explicit_settings.py`](client_with_explicit_settings.py) | Responses client with explicit model and API key settings. |
| [`client_with_file_search.py`](client_with_file_search.py) | Hosted file search sample. |
| [`client_with_function_tools.py`](client_with_function_tools.py) | Function tools with agent-level and run-level patterns. |
| [`client_with_hosted_mcp.py`](client_with_hosted_mcp.py) | Hosted MCP tools and approval workflows. |
| [`client_with_local_mcp.py`](client_with_local_mcp.py) | Local MCP integration with the responses client. |
| [`client_with_local_shell.py`](client_with_local_shell.py) | Local shell tool sample. |
| [`client_with_runtime_json_schema.py`](client_with_runtime_json_schema.py) | Runtime JSON schema output with the responses client. |
| [`client_with_session.py`](client_with_session.py) | Session management with the responses client. |
| [`client_with_shell.py`](client_with_shell.py) | Hosted shell tool sample. |
| [`client_with_structured_output.py`](client_with_structured_output.py) | Structured output with Pydantic models. |
| [`client_with_web_search.py`](client_with_web_search.py) | Web search with the responses client. |

## Environment Variables

Set these before running the OpenAI provider samples:

- `OPENAI_API_KEY`
- `OPENAI_MODEL`

Optionally, you can also set:

- `OPENAI_ORG_ID`
- `OPENAI_BASE_URL`

If your shell also contains `AZURE_OPENAI_*` variables, these samples still stay on OpenAI as long as
`OPENAI_API_KEY` is present. To force Azure routing with the generic clients, pass an explicit Azure
input such as `credential`, `azure_endpoint`, or `api_version`, or use the Azure provider samples.

## Optional Dependencies

Some samples need extra packages:

- `client_image_generation.py` and `client_streaming_image_generation.py` use Pillow for image display.
- MCP samples require the relevant MCP server/tooling you configure locally.
