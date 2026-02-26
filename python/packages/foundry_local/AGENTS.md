# Foundry Local Package (agent-framework-foundry-local)

Integration with Azure AI Foundry Local for local model inference.

## Main Classes

- **`FoundryLocalClient`** - Chat client for Foundry Local models
- **`FoundryLocalChatOptions`** - Options TypedDict for Foundry Local parameters
- **`FoundryLocalSettings`** - Pydantic settings for configuration

## Usage

```python
from agent_framework_foundry_local import FoundryLocalClient

client = FoundryLocalClient(model_id="your-local-model")
response = await client.get_response("Hello")
```

## Import Path

```python
from agent_framework_foundry_local import FoundryLocalClient
```
