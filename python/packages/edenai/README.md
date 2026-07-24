# Get Started with Microsoft Agent Framework Eden AI

Please install this package as the extra for `agent-framework`:

```bash
pip install agent-framework-edenai --pre
```

Eden AI is a gateway to many model providers behind one OpenAI compatible API and a single key. Models use the `provider/model` format, for example `openai/gpt-4o-mini` or `anthropic/claude-sonnet-4-5`.

```python
from agent_framework.edenai import EdenAIChatClient

# Reads EDENAI_API_KEY from the environment, or pass api_key=...
client = EdenAIChatClient(model="openai/gpt-4o-mini")
response = await client.get_response("Hello")
```

See the [README](https://github.com/microsoft/agent-framework/tree/main/python/README.md) for more information.
