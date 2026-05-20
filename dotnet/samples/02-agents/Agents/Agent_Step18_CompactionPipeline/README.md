# Compaction Pipeline

This sample demonstrates how to use a `CompactionProvider` with a `PipelineCompactionStrategy` to manage long conversation histories in a token-efficient way. The pipeline chains four compaction strategies, ordered from gentle to aggressive, so that the least disruptive strategy runs first and more aggressive strategies only activate when necessary.

## What This Sample Shows

- **`CompactionProvider`** — an `AIContextProvider` that applies a compaction strategy before each agent invocation, keeping only the most relevant messages within the model's context window
- **`PipelineCompactionStrategy`** — chains multiple compaction strategies into an ordered pipeline; each strategy evaluates its own trigger independently and operates on the output of the previous one
- **`ToolResultCompactionStrategy`** — collapses older tool-call groups into concise inline summaries, activated by a message-count trigger
- **`SummarizationCompactionStrategy`** — uses an LLM to compress older conversation spans into a single summary message, activated by a token-count trigger
- **`SlidingWindowCompactionStrategy`** — retains only the most recent N user turns and their responses, activated by a turn-count trigger
- **`TruncationCompactionStrategy`** — emergency backstop that drops the oldest groups until the conversation fits within a hard token budget
- **`CompactionTriggers`** — factory methods (`MessagesExceed`, `TokensExceed`, `TurnsExceed`, `GroupsExceed`, `HasToolCalls`, `All`, `Any`) that control when each strategy activates

## Concepts

### Message groups

The compaction engine organizes messages into atomic *groups* that are treated as indivisible units during compaction. A group is either:

| Group kind | Contents |
|---|---|
| `System` | System prompt message(s) |
| `User` | A single user message |
| `ToolCall` | One assistant message with tool calls + the matching tool result messages |
| `AssistantText` | A single assistant text-only message |
| `Summary` | One or more messages summarizing earlier conversation spans, produced by compaction strategies |

`Summary` groups (`CompactionGroupKind.Summary`) are created by compaction strategies (for example, `SummarizationCompactionStrategy`) and do not originate directly from user or assistant messages.
Strategies exclude entire groups rather than individual messages, preserving the tool-call/result pairing required by most model APIs.

### Compaction triggers

A `CompactionTrigger` is a predicate evaluated against the current `MessageIndex`. When the trigger fires, the strategy performs compaction; when it does not fire, the strategy is skipped. Available triggers are:

| Trigger | Activates when… |
|---|---|
| `CompactionTriggers.Always` | Always (unconditional) |
| `CompactionTriggers.Never` | Never (disabled) |
| `CompactionTriggers.MessagesExceed(n)` | Included message count > n |
| `CompactionTriggers.TokensExceed(n)` | Included token count > n |
| `CompactionTriggers.TurnsExceed(n)` | Included user-turn count > n |
| `CompactionTriggers.GroupsExceed(n)` | Included group count > n |
| `CompactionTriggers.HasToolCalls()` | At least one included tool-call group exists |
| `CompactionTriggers.All(...)` | All supplied triggers fire (logical AND) |
| `CompactionTriggers.Any(...)` | Any supplied trigger fires (logical OR) |

### Pipeline ordering

Order strategies from **least aggressive** to **most aggressive**. The pipeline runs every strategy whose trigger is met. Earlier strategies reduce the conversation gently so that later, more destructive strategies may not need to activate at all.

```
1. ToolResultCompactionStrategy  – gentle:    replaces verbose tool results with a short label
2. SummarizationCompactionStrategy – moderate: LLM-summarizes older turns
3. SlidingWindowCompactionStrategy – aggressive: drops turns beyond the window
4. TruncationCompactionStrategy   – emergency:  hard token-budget enforcement
```

## Prerequisites

- .NET 10 SDK or later
- Azure OpenAI service endpoint and model deployment
- Azure CLI installed and authenticated

**Note**: This sample uses `DefaultAzureCredential`. Sign in with `az login` before running. For production, prefer a specific credential such as `ManagedIdentityCredential`. For more information, see the [Azure CLI authentication documentation](https://learn.microsoft.com/cli/azure/authenticate-azure-cli-interactively).

## Environment Variables

```powershell
$env:AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"  # Required
$env:AZURE_OPENAI_DEPLOYMENT_NAME="gpt-5.4-mini"                      # Optional, defaults to gpt-5.4-mini
```

## Running the Sample

```powershell
cd dotnet/samples/02-agents/Agents/Agent_Step18_CompactionPipeline
dotnet run
```

## Expected Behavior

The sample runs a seven-turn shopping-assistant conversation with tool calls. After each turn it prints the full message count so you can observe the pipeline compaction doesn't alter the source conversation.

Each of the four compaction strategies has a deliberately low threshold so that it activates during the short demonstration conversation. In a production scenario you would raise the thresholds to match your model's context window and cost requirements.

## Customizing the Pipeline

### Using a single strategy

If you only need one compaction strategy, pass it directly to `CompactionProvider` without wrapping it in a pipeline:

```csharp
CompactionProvider provider =
    new(new SlidingWindowCompactionStrategy(CompactionTriggers.TurnsExceed(20)));
```

### Ad-hoc compaction outside the provider pipeline

`CompactionProvider.CompactAsync` applies a strategy to an arbitrary list of messages without an active agent session:

```csharp
IEnumerable<ChatMessage> compacted = await CompactionProvider.CompactAsync(
    new TruncationCompactionStrategy(CompactionTriggers.TokensExceed(8000)),
    existingMessages);
```

### Using a different model for summarization

The `SummarizationCompactionStrategy` accepts any `IChatClient`. Use a smaller, cheaper model to reduce summarization cost:

```csharp
IChatClient summarizerChatClient = openAIClient.GetChatClient("gpt-5.4-mini").AsIChatClient();
new SummarizationCompactionStrategy(summarizerChatClient, CompactionTriggers.TokensExceed(4000))
```

### Registering through `ChatClientAgentOptions`

`CompactionProvider` can also be specified directly on `ChatClientAgentOptions` instead of calling `UseAIContextProviders` on the `ChatClientBuilder`:

```csharp
AIAgent agent = agentChatClient
    .AsBuilder()
    .BuildAIAgent(new ChatClientAgentOptions
    {
        AIContextProviders = [new CompactionProvider(compactionPipeline)]
    });
```

This places the compaction provider at the agent level instead of the chat client level, which allows you to use different compaction strategies for different agents that share the same chat client.

> Note: In this mode the `CompactionProvider` is not engaged during the tool calling loop. Agent-level `AIContextProviders` run before chat history is stored, so any synthetic summary messages produced by `CompactionProvider` can become part of the persisted history when using `ChatHistoryProvider`. If you want to compact only the request context while preserving the original stored history, register `CompactionProvider` on the `ChatClientBuilder` via `UseAIContextProviders(...)` instead of on `ChatClientAgentOptions`.
