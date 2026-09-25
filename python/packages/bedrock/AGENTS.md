# Bedrock Package (agent-framework-bedrock)

Integration with AWS Bedrock for LLM inference.

## Main Classes

- **`BedrockChatClient`** - Chat client for AWS Bedrock models
- **`BedrockChatOptions`** - Options TypedDict for Bedrock-specific parameters
- **`BedrockGuardrailConfig`** - Configuration for Bedrock guardrails
- **`BedrockSettings`** - Pydantic settings for Bedrock configuration
- **`BedrockKnowledgeBaseProvider`** - The public entry point for using an Amazon Bedrock Knowledge Base with an agent. A single `ContextProvider` with a `mode`: `"inject"` (inject retrieved passages as context), `"tool"` (expose a KB search tool the model can call), or `"both"` (default). Uses agentic retrieval (query decomposition + managed reranking) with fallback to standard Retrieve, and injects image/audio/video passages as multi-modal `Content`.
- **`BedrockKnowledgeBaseSettings`** - Settings TypedDict for KB region/credentials resolution (`BEDROCK_*`)

## Usage

```python
from agent_framework.amazon import BedrockChatClient

client = BedrockChatClient(model="anthropic.claude-3-sonnet-20240229-v1:0")
response = await client.get_response("Hello")
```

## Import Path

```python
from agent_framework.amazon import BedrockChatClient
```
