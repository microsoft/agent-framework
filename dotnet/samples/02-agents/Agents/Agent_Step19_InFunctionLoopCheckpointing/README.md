# In-Function-Loop Checkpointing

This sample demonstrates how `ChatClientAgent` can persist chat history after each individual call to the AI service using the `RequirePerServiceCallChatHistoryPersistence` option. This per-service-call persistence ensures intermediate progress is saved during the function invocation loop.

## What This Sample Shows

When an agent uses tools, the `FunctionInvokingChatClient` loops multiple times (service call → tool execution → service call → …). By enabling `RequirePerServiceCallChatHistoryPersistence = true`, chat history is persisted after each service call via the `PerServiceCallChatHistoryPersistingChatClient` decorator:

- A `PerServiceCallChatHistoryPersistingChatClient` decorator is inserted into the chat client pipeline
- Before each service call, the decorator loads history from the `ChatHistoryProvider` and prepends it to the request
- After each service call, the decorator notifies the `ChatHistoryProvider` (and any `AIContextProvider` instances) with the new messages
- Only **new** messages are sent to providers on each notification — messages that were already persisted in an earlier call within the same run are deduplicated automatically

By default (without `RequirePerServiceCallChatHistoryPersistence`), chat history is persisted at the end of the full agent run instead. To use per-service-call persistence, set `RequirePerServiceCallChatHistoryPersistence = true` on `ChatClientAgentOptions`.

With `RequirePerServiceCallChatHistoryPersistence` = true, the behavior matches that of chat history stored in the underlying AI service exactly.

Per-service-call persistence is useful for:
- **Crash recovery** — if the process is interrupted mid-loop, the intermediate tool calls and results are already persisted
- **Observability** — you can inspect the chat history while the agent is still running (e.g., during streaming)
- **Long-running tool loops** — agents with many sequential tool calls benefit from incremental persistence

## How It Works

The sample asks the agent about the weather and time in three cities. The model calls the `GetWeather` and `GetTime` tools for each city, resulting in multiple service calls within a single `RunStreamingAsync` invocation. After the run completes, the sample prints the full chat history to show all the intermediate messages that were persisted along the way.

### Pipeline Architecture

```
ChatClientAgent
  └─ FunctionInvokingChatClient    (handles tool call loop)
       └─ PerServiceCallChatHistoryPersistingChatClient  (persists after each service call)
            └─ Leaf IChatClient            (Azure OpenAI)
```

## Prerequisites

- .NET 10 SDK or later
- Azure OpenAI service endpoint and model deployment
- Azure CLI installed and authenticated

**Note**: This sample uses `DefaultAzureCredential`. Sign in with `az login` before running. For production, prefer a specific credential such as `ManagedIdentityCredential`. For more information, see the [Azure CLI authentication documentation](https://learn.microsoft.com/cli/azure/authenticate-azure-cli-interactively).

## Environment Variables

```powershell
$env:AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"  # Required
$env:AZURE_OPENAI_DEPLOYMENT_NAME="gpt-4o-mini"                       # Optional, defaults to gpt-4o-mini
```

## Running the Sample

```powershell
cd dotnet/samples/02-agents/Agents/Agent_Step19_InFunctionLoopCheckpointing
dotnet run
```

## Expected Behavior

The sample runs two conversation turns:

1. **First turn** — asks about weather and time in three cities. The model calls `GetWeather` and `GetTime` tools (potentially in parallel or sequentially), then provides a summary. The chat history dump after the run shows all the intermediate tool call and result messages.

2. **Second turn** — asks a follow-up question ("Which city is the warmest?") that uses the persisted conversation context. The chat history dump shows the full accumulated conversation.

The chat history printout uses `session.TryGetInMemoryChatHistory()` to inspect the in-memory storage.
