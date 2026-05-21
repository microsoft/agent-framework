# Agent with Memory Using Valkey

This sample demonstrates using Valkey for both persistent chat history and long-term memory context with the Agent Framework.

## Components

- **ValkeyChatHistoryProvider** — Persists conversation history across sessions using Valkey lists. Works with any Valkey or Redis OSS server (no search module required).
- **ValkeyContextProvider** — Stores and retrieves memories using Valkey's native full-text search (`FT.SEARCH`). Requires valkey-search >= 1.2.

## Prerequisites

- Azure OpenAI endpoint and deployment
- Valkey 9.1+ with valkey-search module:

```bash
docker run -d --name valkey -p 6379:6379 valkey/valkey-bundle:9.1.0-rc1
```

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint URL | (required) |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | Model deployment name | `gpt-5.4-mini` |
| `VALKEY_CONNECTION` | Valkey connection string | `localhost:6379` |

## Running

```bash
dotnet run
```
