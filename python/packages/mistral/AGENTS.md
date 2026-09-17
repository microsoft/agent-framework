# Mistral Package (agent-framework-mistral)

Integration with Mistral AI for chat completions and embedding generation.

## Implementation Notes

- Uses the official `mistralai` SDK for chat completion and embedding requests.
- Framework message, option, response, and exception translation stays in this package.

## Main Classes

- **`MistralChatClient`** - Chat client for Mistral AI models with function invocation, middleware, and telemetry
- **`RawMistralChatClient`** - Chat client without the batteries-included layers
- **`MistralChatOptions`** - Options TypedDict for Mistral-specific chat parameters
- **`MistralSettings`** - TypedDict settings for Mistral chat configuration
- **`MistralEmbeddingClient`** - Embedding client for Mistral AI models
- **`MistralEmbeddingOptions`** - Options TypedDict for Mistral-specific embedding parameters
- **`MistralEmbeddingSettings`** - TypedDict settings for Mistral configuration

## Usage

```python
from agent_framework import Agent
from agent_framework.mistral import MistralChatClient

# Requires MISTRAL_API_KEY environment variable (or pass api_key= directly)
client = MistralChatClient(model="mistral-large-latest")
try:
    agent = Agent(client=client)
    result = await agent.run("Hello!")
finally:
    await client.close()
```

```python
from agent_framework.mistral import MistralEmbeddingClient

# Requires MISTRAL_API_KEY environment variable (or pass api_key= directly)
client = MistralEmbeddingClient(model="mistral-embed")
try:
    result = await client.get_embeddings(["Hello, world!"])
    print(result[0].vector)
finally:
    await client.close()
```

## Import Path

```python
from agent_framework.mistral import MistralChatClient, MistralEmbeddingClient
```
