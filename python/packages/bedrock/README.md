# Get Started with Microsoft Agent Framework Bedrock

Install the provider package:

```bash
pip install agent-framework-bedrock --pre
```

## Bedrock Integration

The Bedrock integration enables Microsoft Agent Framework applications to call Amazon Bedrock models with familiar chat abstractions, including tool/function calling when you attach tools through `ChatOptions`.

### Basic Usage Example

See the [Bedrock sample](../../samples/02-agents/providers/amazon/bedrock_chat_client.py) for a runnable end-to-end script that:

- Loads credentials from the `BEDROCK_*` environment variables
- Instantiates `BedrockChatClient`
- Sends a simple conversation turn and prints the response

### Knowledge Base Examples

For Amazon Bedrock managed Knowledge Base retrieval, use `BedrockKnowledgeBaseProvider`. Its `mode` selects `"inject"` (inject KB context automatically), `"tool"` (expose a KB search tool the agent calls on demand), or `"both"` (default). See:

- [`bedrock_kb_tool.py`](../../samples/02-agents/providers/amazon/bedrock_kb_tool.py) — `BedrockKnowledgeBaseProvider(mode="tool")`: the agent searches the KB on demand.
- [`bedrock_kb_context_provider.py`](../../samples/02-agents/providers/amazon/bedrock_kb_context_provider.py) — `BedrockKnowledgeBaseProvider(mode="inject")`: KB context is injected automatically.
