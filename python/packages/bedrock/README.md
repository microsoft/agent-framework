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

For Amazon Bedrock managed Knowledge Base retrieval, see:

- [`bedrock_kb_tool.py`](../../samples/02-agents/providers/amazon/bedrock_kb_tool.py) — `BedrockKnowledgeBaseTool` as a `FunctionTool` the agent calls on demand.
- [`bedrock_kb_context_provider.py`](../../samples/02-agents/providers/amazon/bedrock_kb_context_provider.py) — `BedrockKnowledgeBaseProvider` as a `ContextProvider` that injects KB context automatically.
