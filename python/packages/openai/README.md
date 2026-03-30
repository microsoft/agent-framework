# agent-framework-openai

OpenAI integration for Microsoft Agent Framework.

This package provides:

- `OpenAIChatClient` for the OpenAI Responses API
- `OpenAIChatCompletionClient` for the Chat Completions API
- `OpenAIEmbeddingClient` for embeddings

## Installation

```bash
pip install agent-framework-openai --pre
```

## Which chat client should I use?

Use `OpenAIChatClient` for new work unless you specifically need the Chat Completions API.

- `OpenAIChatClient` uses the Responses API and is the preferred general-purpose chat client.
- `OpenAIChatCompletionClient` uses the Chat Completions API and is mainly for compatibility with
  existing Chat Completions-based integrations.

The deprecated `OpenAIResponsesClient` alias points to `OpenAIChatClient`.

## Environment variables

### OpenAI

These variables are used when the client is configured for OpenAI:

| Variable | Purpose |
| --- | --- |
| `OPENAI_API_KEY` | OpenAI API key |
| `OPENAI_ORG_ID` | OpenAI organization ID |
| `OPENAI_BASE_URL` | Custom OpenAI-compatible base URL |
| `OPENAI_MODEL` | Generic fallback model |
| `OPENAI_RESPONSES_MODEL` | Preferred model for `OpenAIChatClient` |
| `OPENAI_CHAT_MODEL` | Preferred model for `OpenAIChatCompletionClient` |
| `OPENAI_EMBEDDING_MODEL` | Preferred model for `OpenAIEmbeddingClient` |

Model lookup order:

- `OpenAIChatClient`: `OPENAI_RESPONSES_MODEL` -> `OPENAI_MODEL`
- `OpenAIChatCompletionClient`: `OPENAI_CHAT_MODEL` -> `OPENAI_MODEL`
- `OpenAIEmbeddingClient`: `OPENAI_EMBEDDING_MODEL` -> `OPENAI_MODEL`

### Azure OpenAI

These variables are used when the client is configured for Azure OpenAI:

| Variable | Purpose |
| --- | --- |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI resource endpoint |
| `AZURE_OPENAI_BASE_URL` | Full Azure OpenAI base URL (`.../openai/v1`) |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI API key |
| `AZURE_OPENAI_API_VERSION` | Azure OpenAI API version |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | Generic fallback deployment |
| `AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME` | Preferred deployment for `OpenAIChatClient` |
| `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME` | Preferred deployment for `OpenAIChatCompletionClient` |
| `AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME` | Preferred deployment for `OpenAIEmbeddingClient` |

Deployment lookup order:

- `OpenAIChatClient`: `AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME` -> `AZURE_OPENAI_DEPLOYMENT_NAME`
- `OpenAIChatCompletionClient`: `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME` -> `AZURE_OPENAI_DEPLOYMENT_NAME`
- `OpenAIEmbeddingClient`: `AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME` -> `AZURE_OPENAI_DEPLOYMENT_NAME`

When both OpenAI and Azure environment variables are present, the generic clients prefer OpenAI
when `OPENAI_API_KEY` is configured. To use Azure explicitly, pass `azure_endpoint` or
`credential`.

## OpenAI example

```python
from agent_framework.openai import OpenAIChatClient

client = OpenAIChatClient(model="gpt-4.1")
```

## Azure OpenAI example

```python
from azure.identity.aio import AzureCliCredential

from agent_framework.openai import OpenAIChatClient

client = OpenAIChatClient(
    model="my-responses-deployment",
    azure_endpoint="https://my-resource.openai.azure.com",
    credential=AzureCliCredential(),
)
```

## ChatClient vs ChatCompletionClient

Use `OpenAIChatClient` when you want the Responses API as your default chat surface.

Use `OpenAIChatCompletionClient` when you specifically need the Chat Completions API:

```python
from agent_framework.openai import OpenAIChatCompletionClient

client = OpenAIChatCompletionClient(model="gpt-4o-mini")
```
