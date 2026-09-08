# agent-framework-openai

OpenAI integration for Microsoft Agent Framework.

This package provides:

- `OpenAIChatClient` for the OpenAI Responses API
- `OpenAIChatCompletionClient` for the Chat Completions API
- `OpenAIEmbeddingClient` for embeddings

## Installation

```bash
pip install agent-framework-openai
```

## Which chat client should I use?

Use `OpenAIChatClient` for new work unless you specifically need the Chat Completions API.

- `OpenAIChatClient` uses the Responses API and is the preferred general-purpose chat client.
- `OpenAIChatCompletionClient` uses the Chat Completions API and is mainly for compatibility with
  existing Chat Completions-based integrations.

The previous deprecated Responses alias has been removed. Use `OpenAIChatClient` directly.

## Environment variables

### OpenAI

These variables are used when the client is configured for OpenAI:

| Variable | Purpose |
| --- | --- |
| `OPENAI_API_KEY` | OpenAI API key |
| `OPENAI_ORG_ID` | OpenAI organization ID |
| `OPENAI_BASE_URL` | Custom OpenAI-compatible base URL |
| `OPENAI_MODEL` | Generic fallback model |
| `OPENAI_CHAT_MODEL` | Preferred model for `OpenAIChatClient` |
| `OPENAI_CHAT_COMPLETION_MODEL` | Preferred model for `OpenAIChatCompletionClient` |
| `OPENAI_EMBEDDING_MODEL` | Preferred model for `OpenAIEmbeddingClient` |

Model lookup order:

- `OpenAIChatClient`: `OPENAI_CHAT_MODEL` -> `OPENAI_MODEL`
- `OpenAIChatCompletionClient`: `OPENAI_CHAT_COMPLETION_MODEL` -> `OPENAI_MODEL`
- `OpenAIEmbeddingClient`: `OPENAI_EMBEDDING_MODEL` -> `OPENAI_MODEL`

These model variables are only consulted when you do not pass `model=` directly. In other words,
`OpenAIChatClient(model="...")` ignores `OPENAI_CHAT_MODEL`, and
`OpenAIChatCompletionClient(model="...")` ignores `OPENAI_CHAT_COMPLETION_MODEL`.

### Azure OpenAI

These variables are used when the client is configured for Azure OpenAI:

| Variable | Purpose |
| --- | --- |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI resource endpoint |
| `AZURE_OPENAI_BASE_URL` | Full Azure OpenAI base URL (`.../openai/v1`) |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI API key |
| `AZURE_OPENAI_API_VERSION` | Azure OpenAI API version |
| `AZURE_OPENAI_MODEL` | Generic fallback deployment |
| `AZURE_OPENAI_CHAT_MODEL` | Preferred deployment for `OpenAIChatClient` |
| `AZURE_OPENAI_CHAT_COMPLETION_MODEL` | Preferred deployment for `OpenAIChatCompletionClient` |
| `AZURE_OPENAI_EMBEDDING_MODEL` | Preferred deployment for `OpenAIEmbeddingClient` |

Deployment lookup order:

- `OpenAIChatClient`: `AZURE_OPENAI_CHAT_MODEL` -> `AZURE_OPENAI_MODEL`
- `OpenAIChatCompletionClient`: `AZURE_OPENAI_CHAT_COMPLETION_MODEL` -> `AZURE_OPENAI_MODEL`
- `OpenAIEmbeddingClient`: `AZURE_OPENAI_EMBEDDING_MODEL` -> `AZURE_OPENAI_MODEL`

For Azure routing, the same rule applies: the client-specific deployment variable is checked first,
then the generic `AZURE_OPENAI_MODEL` fallback. Passing `model=` overrides both environment variables.

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

## Concurrent reuse

This contract applies to the Responses API `OpenAIChatClient`, not the `OpenAIChatCompletionClient` shown above.
An `OpenAIChatClient` instance can be shared by concurrent asynchronous calls on the same event loop. Streaming,
non-streaming, and mixed calls are supported. Keep mutable run state isolated by creating a separate `Agent` and
`AgentSession` for each concurrent run and by passing separate messages and options.

This guarantee does not extend to user-supplied middleware, tools, or callbacks unless those implementations are
also safe for concurrent use. Do not share one client across OS threads or event loops, and do not mutate its
configuration while calls are active.
