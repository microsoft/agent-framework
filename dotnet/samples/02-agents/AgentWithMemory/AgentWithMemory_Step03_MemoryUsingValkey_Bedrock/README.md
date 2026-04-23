# Agent with Memory Using Valkey + Amazon Bedrock

This sample demonstrates using Valkey for both persistent chat history and long-term memory context with the Agent Framework, powered by Amazon Bedrock via the `AWSSDK.Extensions.Bedrock.MEAI` adapter.

## Components

- **ValkeyChatHistoryProvider** — Persists conversation history across sessions using Valkey lists. Works with any Valkey or Redis OSS server (no search module required).
- **ValkeyContextProvider** — Stores and retrieves memories using Valkey's native full-text search (`FT.SEARCH`). Requires valkey-search >= 1.2.
- **Amazon Bedrock** — Provides the LLM via `AWSSDK.Extensions.Bedrock.MEAI`, which implements `IChatClient` from `Microsoft.Extensions.AI`.

## Prerequisites

- AWS credentials configured (environment variables, AWS CLI profile, or IAM role)
- Access to an Amazon Bedrock model (e.g., Anthropic Claude 3.5 Sonnet)
- Valkey 9.1+ with valkey-search module:

```bash
docker run -d --name valkey -p 6379:6379 valkey/valkey-bundle:9.1.0-rc1
```

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `AWS_REGION` | AWS region for Bedrock | `us-east-1` |
| `BEDROCK_MODEL_ID` | Bedrock model identifier | `anthropic.claude-3-5-sonnet-20241022-v2:0` |
| `VALKEY_CONNECTION` | Valkey connection string | `localhost:6379` |
| `AWS_ACCESS_KEY_ID` | AWS access key (if not using profile/role) | — |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key (if not using profile/role) | — |

## Running

```bash
# Using default AWS credential chain (profile, env vars, or IAM role)
dotnet run

# Or with explicit credentials
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
export AWS_REGION="us-east-1"
dotnet run
```
