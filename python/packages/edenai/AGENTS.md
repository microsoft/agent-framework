# Eden AI Package (agent-framework-edenai)

Integration with Eden AI, a gateway to many model providers behind one OpenAI compatible API.

## Main Classes

- **`EdenAIChatClient`** - Chat client for Eden AI models (OpenAI compatible)
- **`EdenAIChatOptions`** - Options TypedDict for Eden AI chat parameters
- **`EdenAISettings`** - Settings for configuration

## Usage

```python
from agent_framework.edenai import EdenAIChatClient

client = EdenAIChatClient(model="openai/gpt-4o-mini")
response = await client.get_response("Hello")
```

## Import Path

```python
from agent_framework.edenai import EdenAIChatClient
```

## Configuration

- `EDENAI_API_KEY`: the Eden AI API key.
- `EDENAI_MODEL`: the `provider/model` to use, for example `openai/gpt-4o-mini`.
- `EDENAI_BASE_URL`: optional, defaults to `https://api.edenai.run/v3`.
