# Gemini Package (agent-framework-gemini)

Integration with Google's Gemini API via the `google-genai` SDK.

## Main Classes

- **`GeminiChatClient`** - Chat client for Google Gemini models
- **`GeminiChatOptions`** - Options TypedDict for Gemini-specific parameters
- **`ThinkingConfig`** - Configuration for extended thinking (Gemini 2.5+)

## Usage

```python
from agent_framework_gemini import GeminiChatClient

client = GeminiChatClient(model_id="gemini-2.5-flash")
response = await client.get_response("Hello")
```

## Import Path

```python
from agent_framework_gemini import GeminiChatClient
```
