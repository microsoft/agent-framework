# Mistral Package (agent-framework-mistral)

Integration with Mistral AI for embedding generation.

## Main Classes

- **`MistralEmbeddingClient`** - Embedding client for Mistral AI models
- **`MistralEmbeddingOptions`** - Options TypedDict for Mistral-specific embedding parameters
- **`MistralEmbeddingSettings`** - TypedDict settings for Mistral configuration

## Usage

```python
from agent_framework_mistral import MistralEmbeddingClient

# Requires MISTRAL_API_KEY environment variable (or pass api_key= directly)
client = MistralEmbeddingClient(model="mistral-embed")
result = await client.get_embeddings(["Hello, world!"])
print(result[0].vector)
```

## Import Path

```python
from agent_framework_mistral import MistralEmbeddingClient
```
