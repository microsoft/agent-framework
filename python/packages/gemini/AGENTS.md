# Gemini Package (agent-framework-gemini)

Integration with Google's Gemini Developer API and Enterprise (Vertex AI) via the `google-genai` SDK.
The shared `_sdk_client.create_genai_client` resolves authentication, backend mode,
and service URL for chat and embeddings.

## Core Classes

- **`RawGeminiChatClient`** - Lightweight chat client without any layers, for custom pipeline composition
- **`GeminiChatClient`** - Full-featured chat client with function invocation, middleware, and telemetry
- **`GeminiChatOptions`** - Options TypedDict for Gemini-specific parameters
- **`GoogleGeminiSettings`** - Shared `GOOGLE_*` environment settings for chat and embeddings
- **`ThinkingConfig`** - Configuration for extended thinking
- **`RawGeminiEmbeddingClient`** - Text and multimodal embeddings without telemetry
- **`GeminiEmbeddingClient`** - Text and multimodal embeddings with telemetry (defaults to stable `gemini-embedding-2`)
- **`GeminiEmbeddingOptions`** - Per-call embedding model, dimensions, text task, and document title

`GeminiEmbeddingClient` supports only `gemini-embedding-2` and `gemini-embedding-2-preview`,
requiring per-call task instructions for text strings. Multimodal Google SDK `Content` or
media `Part` inputs receive no task prefix, even with mixed text-and-media parts. Text-only
SDK content is rejected so callers cannot bypass the task requirement. Enterprise accepts
one content per request; the client splits batches there while keeping input order.

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
from agent_framework.gemini import GeminiChatClient

client = GeminiChatClient(model="gemini-2.5-flash")
response = await client.get_response([Message(role="user", contents=[Content.from_text("Hello")])])
```

```python
from agent_framework.gemini import GeminiEmbeddingClient

client = GeminiEmbeddingClient()
try:
    result = await client.get_embeddings(
        ["A document"], options={"task_type": "RETRIEVAL_DOCUMENT", "dimensions": 768}
    )
finally:
    await client.close()
```
