# Context Compaction Pipeline

This sample demonstrates how to configure a `PipelineCompactionStrategy` as the in-run compaction strategy for an AI agent, chaining multiple built-in strategies from gentlest to most aggressive to keep conversation context within token limits during long, tool-heavy conversations.

## What this sample demonstrates

- Configuring `ChatClientAgentOptions.CompactionStrategy` with a `PipelineCompactionStrategy`
- Chaining four complementary strategies to form a graduated compaction pipeline:
  1. **`ToolResultCompactionStrategy`** – Collapses old tool-call groups into single summary lines (`[Tool calls: LookupPrice]`), the least-destructive option
  2. **`SummarizationCompactionStrategy`** – Uses a second LLM call to distill older conversation spans into a concise assistant message, preserving key facts while freeing tokens
  3. **`SlidingWindowCompactionStrategy`** – Removes the oldest user turns entirely, bounding conversation length on a turn-count basis
  4. **`TruncationCompactionStrategy`** – Emergency backstop that drops the oldest groups until the context is within a hard token budget
- Using `CompactionTriggers` to control when each strategy activates (`TokensExceed`, `TurnsExceed`)
- Inspecting live chat history size after each turn to observe compaction in action

## Background: context compaction

Every LLM has a finite context window. In long multi-turn conversations — especially those with tool calls — the accumulated messages eventually exceed the model's token limit, causing errors or degraded responses. Context compaction solves this by pruning, collapsing, or summarizing messages before they are sent to the model.

The framework models compaction as a pipeline of `CompactionStrategy` instances. Each strategy:

- Evaluates a `CompactionTrigger` predicate to decide whether to act
- Operates on a `MessageIndex` that organises messages into atomic **groups**, guaranteeing that assistant messages and their associated tool results are always treated as a unit and never split
- Stops incrementally when an optional **target** condition is satisfied (defaults to the inverse of the trigger)

Strategies can be used individually or composed via `PipelineCompactionStrategy`, which runs each strategy in order against the same `MessageIndex`.

## Built-in strategies

| Strategy | Aggressiveness | Best used for |
|---|---|---|
| `ToolResultCompactionStrategy` | Gentle | Shrinking verbose tool results while retaining a record of which tools were called |
| `SummarizationCompactionStrategy` | Moderate | Preserving conversation intent while freeing large blocks of tokens |
| `SlidingWindowCompactionStrategy` | Aggressive | Bounding conversation length predictably on a per-turn basis |
| `TruncationCompactionStrategy` | Emergency | Hard token-budget enforcement as a last resort |
| `ChatReducerCompactionStrategy` | Varies | Adapting an existing `IChatReducer` implementation into the compaction pipeline |

## Compaction triggers

`CompactionTriggers` provides factory methods for the most common conditions:

| Trigger | Description |
|---|---|
| `TokensExceed(n)` | Fires when the included token count exceeds `n` |
| `TurnsExceed(n)` | Fires when the included user-turn count exceeds `n` |
| `MessagesExceed(n)` | Fires when the included message count exceeds `n` |
| `GroupsExceed(n)` | Fires when the included group count exceeds `n` |
| `HasToolCalls()` | Fires when at least one non-excluded tool-call group is present |
| `All(...)` / `Any(...)` | Combines multiple triggers with logical AND / OR |
| `Always` / `Never` | Unconditional triggers useful for testing or forced compaction |

Custom triggers are plain `CompactionTrigger` delegates (`Func<MessageIndex, bool>`), so any condition expressible in C# can be used.

## Prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 10 SDK or later
- Azure OpenAI service endpoint and deployment configured
- Azure CLI installed and authenticated (for Azure credential authentication)
- User has the `Cognitive Services OpenAI Contributor` role for the Azure OpenAI resource

**Note**: This sample uses Azure CLI credentials for authentication. Make sure you're logged in with `az login` and have access to the Azure OpenAI resource. For more information, see the [Azure CLI documentation](https://learn.microsoft.com/cli/azure/authenticate-azure-cli-interactively).

**Note**: The sample creates two `IChatClient` instances that share the same deployment — one for the agent and one for the `SummarizationCompactionStrategy`. In production, consider pointing the summarizer at a smaller or cheaper model to reduce cost and latency.

**Note**: All compaction APIs carry the `[Experimental]` attribute. Suppress `AGENTSAI001` in your project file if needed:

```xml
<PropertyGroup>
  <NoWarn>$(NoWarn);AGENTSAI001</NoWarn>
</PropertyGroup>
```

## Environment Variables

Set the following environment variables:

```powershell
$env:AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/" # Replace with your Azure OpenAI resource endpoint
$env:AZURE_OPENAI_DEPLOYMENT_NAME="gpt-4o-mini"  # Optional, defaults to gpt-4o-mini
```

## Run the sample

Navigate to the sample directory and run:

```powershell
cd dotnet/samples/02-agents/Agents/Agent_Step18_CompactionPipeline
dotnet run
```

## Expected behavior

The sample runs a seven-turn shopping-assistant conversation that repeatedly calls a `LookupPrice` tool. After each turn the chat-history count is printed so you can observe compaction reducing the number of in-memory messages.

```
User: What's the price of a laptop?
Agent: ...
  [Chat history: 4 messages]

User: How about a keyboard?
Agent: ...
  [Chat history: 8 messages]

...

User: What was the first product I asked about?
Agent: Based on the conversation summary, the first product you asked about was a laptop...
  [Chat history: 6 messages]
```

As the conversation grows, the pipeline fires strategies in order:

1. **`ToolResultCompactionStrategy`** collapses verbose tool-call groups once the token count exceeds 512 tokens (`0x200`), replacing them with `[Tool calls: LookupPrice]`
2. **`SummarizationCompactionStrategy`** summarizes older spans once the token count exceeds 1 280 tokens (`0x500`), inserting a `[Summary]` assistant message in their place
3. **`SlidingWindowCompactionStrategy`** drops the oldest user turns once more than 4 turns are in history
4. **`TruncationCompactionStrategy`** removes the oldest groups when the total exceeds 32 768 tokens (`0x8000`) as an emergency backstop

The agent's final answer about "the first product" demonstrates that the summarization strategy successfully preserved the key fact (laptop) even after older raw messages were removed.

## Key concepts

### Configuring in-run compaction

Assign a `CompactionStrategy` to `ChatClientAgentOptions.CompactionStrategy`. The framework wraps the underlying `IChatClient` with an internal `CompactingChatClient` that applies the strategy before each LLM call during the tool loop:

```csharp
AIAgent agent = agentChatClient.AsAIAgent(new ChatClientAgentOptions
{
    CompactionStrategy = new PipelineCompactionStrategy(
        new ToolResultCompactionStrategy(CompactionTriggers.TokensExceed(512)),
        new SummarizationCompactionStrategy(summarizerChatClient, CompactionTriggers.TokensExceed(1280)),
        new SlidingWindowCompactionStrategy(CompactionTriggers.TurnsExceed(10)),
        new TruncationCompactionStrategy(CompactionTriggers.TokensExceed(32768))),
});
```

### Using a single strategy

`PipelineCompactionStrategy` is optional. A single strategy can be set directly:

```csharp
new ChatClientAgentOptions
{
    CompactionStrategy = new SlidingWindowCompactionStrategy(CompactionTriggers.TurnsExceed(10)),
}
```

### Adapting an existing `IChatReducer`

If you already have an `IChatReducer` implementation (e.g., `MessageCountingChatReducer`), wrap it with `ChatReducerCompactionStrategy` to use it in the pipeline:

```csharp
new ChatReducerCompactionStrategy(
    new MessageCountingChatReducer(maxMessageCount: 20),
    CompactionTriggers.MessagesExceed(20))
```

### Custom trigger

Any `Func<MessageIndex, bool>` can serve as a trigger:

```csharp
CompactionTrigger myTrigger = index =>
    index.IncludedTokenCount > 4096 && index.IncludedTurnCount > 5;
```

### Combining triggers

```csharp
// Fire only when BOTH conditions hold
CompactionTrigger trigger = CompactionTriggers.All(
    CompactionTriggers.TokensExceed(2048),
    CompactionTriggers.HasToolCalls());
```
