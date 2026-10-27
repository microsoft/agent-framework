# Get Started with Microsoft Agent Framework Anthropic

Please install this package via pip:

```bash
pip install agent-framework-anthropic --pre
```

## Anthropic Integration

The Anthropic integration enables communication with the Anthropic API, allowing your Agent Framework applications to leverage Anthropic's capabilities.

The package also includes Anthropic-hosted transport wrappers for:

- Microsoft Foundry via `AnthropicFoundryClient`
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

Instructions contributed later in a run — by a context provider such as `SkillsProvider`, or by per-run
`options` — are appended as an additional text block after the configured blocks. The blocks you supply keep
their structure and their position, so a `cache_control` breakpoint stays valid.

### Persisted server-tool history

Anthropic server-tool calls and results use `Content.additional_properties["anthropic"]["server_tool_block"]`
internally to preserve the native block type, structured result content, and optional caller metadata across
message serialization. Result metadata can contain provider-encrypted fields such as `encrypted_content`; the
adapter stores those plain serialized values unchanged because Anthropic requires them for replay. Applications
should treat this namespace as adapter-owned replay data and must not modify it.

### Paused server-tool turns

When Anthropic returns `pause_turn`, the client automatically replays the paused assistant content with the same
tools when every content block can be reconstructed faithfully. It performs at most 10 continuation requests.
If the paused response contains unsupported native tool content, includes a native block dropped during parsing
(such as redacted reasoning), contains a streamed MCP call whose argument deltas are not retained, or remains paused
after that limit, the response retains `finish_reason="pause_turn"` so the caller can decide whether to continue later.
