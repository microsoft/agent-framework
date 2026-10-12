# Foundry Local Package (agent-framework-foundry-local)

Integration with Microsoft Foundry Local for local model inference.

Uses `foundry_local_sdk` (SDK 2.1+, below 3.0) on Python 3.11-3.14. Clients share
`FoundryLocalManager.instance` and use its built-in web service with the existing
OpenAI transport. Model lifecycle operations live on catalog model objects.

## Main Classes

- **`FoundryLocalClient`** - Chat client for Foundry Local models
- **`FoundryLocalChatOptions`** - Options TypedDict for Foundry Local parameters
- **`FoundryLocalSettings`** - Settings TypedDict for model configuration

## Usage

```python
from agent_framework.foundry import FoundryLocalClient

client = FoundryLocalClient(model="your-local-model")
response = await client.get_response("Hello")
```

## Import Path

```python
from agent_framework.foundry import FoundryLocalClient
```
