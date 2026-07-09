# Get Started with Microsoft Agent Framework Anthropic

Please install this package via pip:

```bash
pip install agent-framework-anthropic --pre
```

## Anthropic Integration

The Anthropic integration enables communication with the Anthropic API, allowing your Agent Framework applications to leverage Anthropic's capabilities.

The package also includes Anthropic-hosted transport wrappers for:

- Azure AI Foundry via `AnthropicFoundryClient`
- Amazon Bedrock via `AnthropicBedrockClient`
- Google Vertex AI via `AnthropicVertexClient`

### Basic Usage Example

See the [Anthropic agent examples](../../samples/02-agents/providers/anthropic/) which demonstrate:

- Connecting to a Anthropic endpoint with an agent
- Streaming and non-streaming responses

### Structured system blocks for prompt caching

Use `instructions` with Anthropic-native system blocks when you need structured system prompt content, such as
prompt-cache `cache_control` metadata. Do not combine structured `instructions` blocks with a leading system message.

```python
from anthropic.types.beta import BetaTextBlockParam

from agent_framework_anthropic import AnthropicClient

client = AnthropicClient()
system_blocks: list[BetaTextBlockParam] = [
    {"type": "text", "text": "Stable instructions", "cache_control": {"type": "ephemeral", "ttl": "1h"}},
]

response = await client.get_response("Hello", options={"instructions": system_blocks})
```
