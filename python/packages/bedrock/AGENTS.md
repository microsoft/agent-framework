# Bedrock Package (agent-framework-bedrock)

Integration with AWS Bedrock for LLM inference.

## Main Classes

- **`BedrockChatClient`** - Chat client for AWS Bedrock models
- **`BedrockChatOptions`** - Options TypedDict for Bedrock-specific parameters
- **`BedrockGuardrailConfig`** - Configuration for Bedrock guardrails
- **`BedrockSettings`** - Pydantic settings for Bedrock configuration

## Usage

```python
from agent_framework.amazon import BedrockChatClient

client = BedrockChatClient(model_id="anthropic.claude-3-sonnet-20240229-v1:0")
response = await client.get_response("Hello")
```

## Import Path

```python
from agent_framework.amazon import BedrockChatClient
```
