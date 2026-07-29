# Get Started with Microsoft Agent Framework Mistral AI

Please install this package:

```bash
pip install agent-framework-mistral --pre
```

and see the [README](https://github.com/microsoft/agent-framework/tree/main/python/README.md) for more information.

See the [Mistral agent sample](../../samples/02-agents/providers/mistral/mistral_agent_basic.py) and the
[Mistral embedding sample](../../samples/02-agents/providers/mistral/mistral_embeddings.py) for runnable examples.

## Chat Client

The `MistralChatClient` provides chat completions using Mistral AI models, with support for
streaming, function tools, and structured output.

### Quick Start

```python
from agent_framework import Agent
from agent_framework.mistral import MistralChatClient

# Using environment variables (MISTRAL_API_KEY, MISTRAL_CHAT_MODEL)
# Parameters can also be passed directly:
# MistralChatClient(model="mistral-large-latest", api_key="your-api-key")
client = MistralChatClient()
try:
    agent = Agent(client=client, instructions="You are a helpful assistant.")
    response = await agent.run("Hello!")
    print(response.text)
finally:
    await client.close()
```

### Configuration

| Environment Variable | Description |
|---|---|
| `MISTRAL_API_KEY` | Your Mistral AI API key |
| `MISTRAL_CHAT_MODEL` | Chat model name (e.g., `mistral-large-latest`) |
| `MISTRAL_SERVER_URL` | Optional server URL override |

## Embedding Client

The `MistralEmbeddingClient` provides embedding generation using Mistral AI models.

### Quick Start

```python
from agent_framework.mistral import MistralEmbeddingClient

# Using environment variables (MISTRAL_API_KEY, MISTRAL_EMBEDDING_MODEL)
client = MistralEmbeddingClient()

try:
    # Parameters can also be passed directly:
    # MistralEmbeddingClient(model="mistral-embed", api_key="your-api-key")
    result = await client.get_embeddings(["Hello, world!", "How are you?"])
    for embedding in result:
        print(f"Dimensions: {embedding.dimensions}")
        print(f"Vector: {embedding.vector[:5]}...")
finally:
    await client.close()
```

### Configuration

| Environment Variable | Description |
|---|---|
| `MISTRAL_API_KEY` | Your Mistral AI API key |
| `MISTRAL_EMBEDDING_MODEL` | Embedding model name (e.g., `mistral-embed`) |
| `MISTRAL_SERVER_URL` | Optional server URL override |
