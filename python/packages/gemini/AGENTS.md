# Gemini Package (agent-framework-gemini)

Integration with Google's Gemini API via the `google-genai` SDK.

## Core Classes

- **`GeminiChatClient`** - Chat client for Google Gemini models
- **`GeminiChatOptions`** - Options TypedDict for Gemini-specific parameters
- **`GeminiSettings`** - Settings loaded from environment variables
- **`ThinkingConfig`** - Configuration for extended thinking

## Gemini Options

- **`thinking_config`** - Enable extended thinking via `ThinkingConfig`
- **`google_search_grounding`** - Responses with live Google Search results
- **`google_maps_grounding`** - Responses with Google Maps data
- **`code_execution`** - Let the model write and run code in a sandboxed environment

## Usage

```python
from agent_framework import Content, Message
from agent_framework_gemini import GeminiChatClient

client = GeminiChatClient(model_id="gemini-2.5-flash")
response = await client.get_response([Message(role="user", contents=[Content.from_text("Hello")])])
```
