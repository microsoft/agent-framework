# Anthropic Package (agent-framework-anthropic)

Integration with Anthropic's Claude API.

## Main Classes

- **`AnthropicClient`** - Chat client for Anthropic Claude models
- **`AnthropicChatOptions`** - Options TypedDict for Anthropic-specific parameters

## Usage

```python
from agent_framework.anthropic import AnthropicClient

client = AnthropicClient(model_id="claude-sonnet-4-20250514")
response = await client.get_response("Hello")
```

## Import Path

```python
from agent_framework.anthropic import AnthropicClient
# or directly:
from agent_framework_anthropic import AnthropicClient
```
