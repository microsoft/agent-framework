# Get Started with Microsoft Agent Framework Mistral AI

Please install this package:

```bash
pip install agent-framework-mistral --pre
```

and see the [README](https://github.com/microsoft/agent-framework/tree/main/python/README.md) for more information.

## Embedding Client

The `MistralEmbeddingClient` provides embedding generation using Mistral AI models.

### Quick Start

```python
from agent_framework_mistral import MistralEmbeddingClient

# Using environment variables (MISTRAL_API_KEY, MISTRAL_EMBEDDING_MODEL)
client = MistralEmbeddingClient()

# Or passing parameters directly
client = MistralEmbeddingClient(
    model="mistral-embed",
    api_key="your-api-key",
)

# Generate embeddings
result = await client.get_embeddings(["Hello, world!", "How are you?"])
for embedding in result:
    print(f"Dimensions: {embedding.dimensions}")
    print(f"Vector: {embedding.vector[:5]}...")
```

### Configuration

| Environment Variable | Description |
|---|---|
| `MISTRAL_API_KEY` | Your Mistral AI API key |
| `MISTRAL_EMBEDDING_MODEL` | Embedding model name (e.g., `mistral-embed`) |
| `MISTRAL_SERVER_URL` | Optional server URL override |
