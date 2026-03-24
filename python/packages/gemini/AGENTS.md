# Gemini Package (agent-framework-gemini)

Integration with Google's Gemini API via the `google-genai` SDK.

## Core Classes

- **`RawGeminiChatClient`** - Lightweight chat client without any layers, for custom pipeline composition
- **`GeminiChatClient`** - Full-featured chat client with function invocation, middleware, and telemetry
- **`GeminiChatOptions`** - Options TypedDict for Gemini-specific parameters
- **`GeminiSettings`** - Settings loaded from environment variables
- **`ThinkingConfig`** - Configuration for extended thinking

## Gemini Options

- **`thinking_config`** - Enable extended thinking via `ThinkingConfig`
- **`code_execution`** - Let the model write and run code in a sandboxed environment
- **`google_search_grounding`** - Responses with live Google Search results
- **`google_maps_grounding`** - Responses with Google Maps data

## Usage

```python
from agent_framework import Content, Message
from agent_framework_gemini import GeminiChatClient

client = GeminiChatClient(model="gemini-2.5-flash")
response = await client.get_response([Message(role="user", contents=[Content.from_text("Hello")])])
```
