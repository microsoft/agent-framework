# Gemini Package (agent-framework-gemini)

Integration with Google's Gemini Developer API and Vertex AI via the `google-genai` SDK.

## Core Classes

- **`RawGeminiChatClient`** - Lightweight chat client without any layers, for custom pipeline composition
- **`GeminiChatClient`** - Full-featured chat client with function invocation, middleware, and telemetry
- **`GeminiChatOptions`** - Options TypedDict for Gemini-specific parameters
- **`GeminiSettings`** - Settings loaded from environment variables
- **`GoogleGeminiSettings`** - SDK-standard `GOOGLE_*` settings loaded from environment variables
- **`ThinkingConfig`** - Configuration for extended thinking

## Gemini-specific Options

- **`thinking_config`** - Enable extended thinking via `ThinkingConfig`
- **`response_schema`** - Raw JSON schema dict for structured output (alternative to `response_format`)
- **`top_k`** - Top-K sampling parameter

## Built-in Tool Factory Methods

- **`get_web_search_tool()`** - Google Search grounding for up-to-date web answers
- **`get_code_interpreter_tool()`** - Sandboxed code execution
- **`get_maps_grounding_tool()`** - Google Maps grounding for location and mapping
- **`get_file_search_tool()`** - Retrieval from Gemini file search stores
- **`get_mcp_tool()`** - Model Context Protocol server integration

## Usage

```python
from agent_framework import Content, Message
from agent_framework_gemini import GeminiChatClient

client = GeminiChatClient(model="gemini-2.5-flash")
response = await client.get_response([Message(role="user", contents=[Content.from_text("Hello")])])
```
