# Ollama Package (agent-framework-ollama)

Integration with Ollama for local LLM inference.

## Main Classes

- **`OllamaChatClient`** - Chat client for Ollama models
- **`OllamaChatOptions`** - Options TypedDict for Ollama-specific parameters
- **`OllamaSettings`** - Pydantic settings for Ollama configuration

## Usage

```python
from agent_framework.ollama import OllamaChatClient

client = OllamaChatClient(model_id="llama3.2")
response = await client.get_response("Hello")
```

## Import Path

```python
from agent_framework.ollama import OllamaChatClient
# or directly:
from agent_framework_ollama import OllamaChatClient
```
