# Anthropic Package (agent-framework-anthropic)

Integration with Anthropic's Claude API.

## Main Classes

- **`AnthropicClient`** - Chat client for Anthropic Claude models
- **`AnthropicFoundryClient`** - Anthropic chat client for Azure AI Foundry's Anthropic-compatible endpoint
- **`AnthropicBedrockClient`** - Anthropic chat client for Amazon Bedrock
- **`AnthropicVertexClient`** - Anthropic chat client for Google Vertex AI
- **`AnthropicChatOptions`** - Options TypedDict for Anthropic-specific parameters

## Usage

```python
from agent_framework.anthropic import AnthropicClient

client = AnthropicClient(model="claude-sonnet-4-20250514")
response = await client.get_response("Hello")
```

## Import Path

```python
from agent_framework.anthropic import AnthropicClient
# or directly:
from agent_framework_anthropic import AnthropicClient
```
