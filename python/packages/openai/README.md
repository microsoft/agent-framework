# agent-framework-openai

OpenAI integration for Microsoft Agent Framework. Provides chat clients for the OpenAI Responses API and Chat Completions API.

## Installation

```bash
pip install agent-framework-openai
```

## Usage

```python
from agent_framework.openai import OpenAIChatClient

client = OpenAIChatClient(model_id="gpt-4o")
```

When both OpenAI and Azure environment variables are present, the generic OpenAI clients prefer
OpenAI whenever `OPENAI_API_KEY` is configured. To force Azure routing, pass an explicit Azure input
such as `credential`, `azure_endpoint`, or `api_version`.
