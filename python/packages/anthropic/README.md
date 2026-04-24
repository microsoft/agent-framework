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
