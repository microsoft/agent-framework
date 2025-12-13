# Get Started with Microsoft Agent Framework Bedrock

Install the provider package:

```bash
pip install agent-framework-bedrock --pre
```

## Bedrock Integration

The Bedrock integration enables Microsoft Agent Framework applications to call Amazon Bedrock models with familiar chat abstractions, including tool/function calling when you attach tools through `ChatOptions`.

### Basic Usage Example

See the [Bedrock sample script](samples/bedrock_sample.py) for a runnable end-to-end script that:

- Loads credentials from the `BEDROCK_*` environment variables
- Instantiates `BedrockChatClient`
- Sends a simple conversation turn and prints the response
