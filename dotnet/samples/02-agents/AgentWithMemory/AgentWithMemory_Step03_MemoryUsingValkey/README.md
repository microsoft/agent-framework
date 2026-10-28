# Agent with Memory Using Valkey

This sample demonstrates using Valkey for persistent chat history with the Agent Framework.

## Components

- **ValkeyChatHistoryProvider** — Persists conversation history across sessions using Valkey lists. Works with any Valkey or Redis OSS server (no search module required).

## Prerequisites

- A Microsoft Foundry project with a deployed model
- A running Valkey server (any version):

```bash
docker run -d --name valkey -p 6379:6379 valkey/valkey:latest
```

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `FOUNDRY_PROJECT_ENDPOINT` | Microsoft Foundry project endpoint | (required) |
| `FOUNDRY_MODEL` | Model deployment name | `gpt-5.4-mini` |
| `VALKEY_CONNECTION` | Valkey connection string | `localhost:6379` |

## Running

```bash
dotnet run
```
