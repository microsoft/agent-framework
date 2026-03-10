# Chat-History Compaction

Long-running agent sessions accumulate chat history that can exceed a model's context window. The **Microsoft Agent Framework** includes a built-in compaction system that automatically manages conversation history before each model call — keeping agents within their token budget without losing important context.

## How It Works

Compaction is wired in as an `AIContextProvider` (`CompactionProvider`), which means it runs before **every** model invocation — including each iteration of the function-calling loop. This is important: the context window is actively managed throughout a tool-use chain, not just at the start of an agent invocation.

The provider groups messages into atomic units, so tool-call/result pairs are always treated as a single unit and never split during compaction.

## Setting Up Compaction

Attach a `CompactionProvider` to any agent via `UseAIContextProviders`:

```csharp
AIAgent agent =
    agentChatClient
        .AsBuilder()
        .UseAIContextProviders(new CompactionProvider(compactionPipeline))
        .BuildAIAgent(new ChatClientAgentOptions { Name = "MyAgent" });
```

## Strategies

Each strategy takes a `CompactionTrigger` that defines *when* it activates — based on token count, message count, turn count, or other metrics (e.g. `CompactionTriggers.TokensExceed(8000)`, `CompactionTriggers.TurnsExceed(4)`).

The built-in strategies range from gentle to aggressive:

- **`ToolResultCompactionStrategy`** — Collapses old tool-call groups into a one-line summary (e.g. `[Tool calls: LookupPrice]`). Preserves all user and assistant messages.
- **`SummarizationCompactionStrategy`** — Uses an LLM to replace older conversation spans with a concise summary, preserving key facts while reducing tokens.
- **`SlidingWindowCompactionStrategy`** — Drops the oldest complete user turns, keeping a bounded window of recent conversation.
- **`TruncationCompactionStrategy`** — Removes the oldest message groups until the context is back under budget. Best used as a last-resort backstop.
- **`ChatReducerCompactionStrategy`** — Adapts any `Microsoft.Extensions.AI.IChatReducer` into the pipeline.

## Composing a Pipeline

For production agents, use `PipelineCompactionStrategy` to chain strategies from least to most aggressive. Each strategy only activates when its trigger fires, so gentle approaches are tried first:

```csharp
PipelineCompactionStrategy compactionPipeline =
    new(// 1. Gentle: collapse old tool-call groups into short summaries
        new ToolResultCompactionStrategy(CompactionTriggers.MessagesExceed(7)),

        // 2. Moderate: LLM-summarize older conversation spans
        new SummarizationCompactionStrategy(summarizerChatClient, CompactionTriggers.TokensExceed(0x500)),

        // 3. Aggressive: keep only the last 4 user turns
        new SlidingWindowCompactionStrategy(CompactionTriggers.TurnsExceed(4)),

        // 4. Emergency: drop oldest groups until under the token budget
        new TruncationCompactionStrategy(CompactionTriggers.TokensExceed(0x8000)));
```

See the [Agent_Step18_CompactionPipeline](https://github.com/microsoft/agent-framework/dotnet/samples/02-agents/Agents/Agent_Step18_CompactionPipeline/Program.cs) sample for a complete working example.
