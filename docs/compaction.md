# Chat-History Compaction

Long-running agent sessions accumulate chat history that can quickly exceed a model's context window. The **Microsoft Agent Framework** addresses this with a built-in compaction system that automatically trims, summarizes, or restructures conversation history before each model call — keeping agents within their token budget while retaining as much useful context as possible.

## How Compaction Works

Compaction is implemented as an [`AIContextProvider`](../dotnet/src/Microsoft.Agents.AI/AIContextProvider.cs) called [`CompactionProvider`](../dotnet/src/Microsoft.Agents.AI/Compaction/CompactionProvider.cs). Because context providers are invoked before **every** chat-client call, compaction fires for all model invocations — including each iteration of the function-calling loop. This means that even in a single agent turn involving multiple tool calls, the message history is re-evaluated and compacted as needed before each LLM request.

```
User Input → AIAgent.RunAsync()
  → AIContextProviderChatClient (invokes context providers)
      → CompactionProvider.InvokingCoreAsync()   ← fires here
          → Organize messages into atomic groups
          → Evaluate trigger condition
          → Apply compaction strategy if triggered
          → Return compacted message list
      → Inner IChatClient.GetResponseAsync()
          → If tool calls returned, execute tools and loop:
              → AIContextProviderChatClient (invokes context providers)
                  → CompactionProvider.InvokingCoreAsync()   ← fires again
                  ...
```

Internally, `CompactionProvider` organizes messages into **atomic groups** — crucially, an assistant message containing tool calls and its corresponding tool result messages are always kept together and compacted as a unit. This preserves the structural integrity of the conversation and prevents models from seeing dangling tool calls without results.

The provider stores its index in `AgentSession.StateBag`, so incremental updates are cheap: only messages added since the last compaction call need to be re-indexed.

## Adding a CompactionProvider to an Agent

Register `CompactionProvider` via `UseAIContextProviders` on a `ChatClientBuilder`, or via `ChatClientAgentOptions.AIContextProviders`:

```csharp
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Compaction;

// Pass any CompactionStrategy to the provider
CompactionProvider compactionProvider = new(new TruncationCompactionStrategy(
    CompactionTriggers.TokensExceed(8000)));

AIAgent agent =
    chatClient
        .AsBuilder()
        .UseAIContextProviders(compactionProvider)
        .BuildAIAgent(new ChatClientAgentOptions { Name = "MyAgent" });
```

Or equivalently via options:

```csharp
AIAgent agent =
    chatClient
        .AsBuilder()
        .BuildAIAgent(new ChatClientAgentOptions
        {
            Name = "MyAgent",
            AIContextProviders = [new CompactionProvider(new TruncationCompactionStrategy(
                CompactionTriggers.TokensExceed(8000)))]
        });
```

## Compaction Triggers

Every strategy requires a `CompactionTrigger` — a predicate over `MessageIndex` metrics that controls *when* the strategy activates. The `CompactionTriggers` factory provides common conditions:

| Trigger | Description |
|---|---|
| `CompactionTriggers.Always` | Fires unconditionally on every invocation |
| `CompactionTriggers.Never` | Never fires (useful for disabling a stage) |
| `CompactionTriggers.TokensExceed(n)` | Fires when the included token count exceeds `n` |
| `CompactionTriggers.TokensBelow(n)` | Fires when the included token count is below `n` |
| `CompactionTriggers.MessagesExceed(n)` | Fires when the included message count exceeds `n` |
| `CompactionTriggers.TurnsExceed(n)` | Fires when the included user-turn count exceeds `n` |
| `CompactionTriggers.GroupsExceed(n)` | Fires when the included group count exceeds `n` |
| `CompactionTriggers.HasToolCalls()` | Fires when there is at least one non-excluded tool-call group |
| `CompactionTriggers.All(t1, t2, ...)` | Logical AND of multiple triggers |
| `CompactionTriggers.Any(t1, t2, ...)` | Logical OR of multiple triggers |

Each strategy also accepts an optional **target** trigger that controls when compaction *stops*. Once the target returns `true`, the strategy stops removing groups even if more could be removed. When no target is provided, the default target is the inverse of the trigger — compaction stops as soon as the trigger condition would no longer fire.

## Compaction Strategies

### `ToolResultCompactionStrategy` — Gentlest

Collapses old tool-call groups (the assistant message + all tool result messages) into a single short assistant message like `[Tool calls: LookupPrice, SearchInventory]`. It never removes user messages or plain assistant responses, so the conversation's narrative structure remains intact.

**Best for:** Agents that make many tool calls per turn, where detailed results from older turns are less important than the overall flow.

```csharp
// Collapse old tool groups once the message count exceeds 10
new ToolResultCompactionStrategy(CompactionTriggers.MessagesExceed(10))
```

### `SummarizationCompactionStrategy` — Moderate

Uses a separate LLM call to generate a concise narrative summary of the oldest conversation groups, replacing them with a single `[Summary]` assistant message. This preserves semantic content that truncation would lose outright.

**Best for:** Conversations where factual context (user preferences, decisions, prior outcomes) must survive long sessions.

```csharp
// Summarize older groups when token count exceeds 1,280
// (use a smaller/cheaper model for the summarizer to keep costs down)
new SummarizationCompactionStrategy(summarizerChatClient, CompactionTriggers.TokensExceed(1280))
```

You can provide a custom summarization prompt via the `summarizationPrompt` parameter, and tune how many recent groups are protected via `minimumPreserved` (default: 4).

### `SlidingWindowCompactionStrategy` — Aggressive

Removes the oldest complete user turns (the user message and all associated assistant/tool groups), keeping a bounded window of the most recent turns.

**Best for:** Scenarios where only the last N turns are relevant (e.g., task-focused assistants with short-lived context needs). More predictable than token-based truncation because it operates on logical turn boundaries.

```csharp
// Drop oldest turns once the turn count exceeds 4
new SlidingWindowCompactionStrategy(CompactionTriggers.TurnsExceed(4))
```

### `TruncationCompactionStrategy` — Most Aggressive

Removes the oldest non-system message groups one at a time until the trigger condition no longer applies. Unlike `SlidingWindowCompactionStrategy`, it works at the group level and can remove partial turns. This strategy is best used as an emergency backstop.

**Best for:** Hard token-budget enforcement when softer strategies haven't brought the context under the limit.

```csharp
// Drop oldest groups until under 32,768 tokens
new TruncationCompactionStrategy(CompactionTriggers.TokensExceed(0x8000))
```

### `PipelineCompactionStrategy` — Composed

Chains multiple strategies from least to most aggressive. Each strategy is applied in order; if the first strategy's trigger does not fire (or if applying it is insufficient), the next strategy is tried. This lets you define a graduated response to growing context.

```csharp
PipelineCompactionStrategy pipeline = new(
    // 1. Gentle: collapse old tool-call groups
    new ToolResultCompactionStrategy(CompactionTriggers.MessagesExceed(7)),

    // 2. Moderate: LLM-summarize older conversation spans
    new SummarizationCompactionStrategy(summarizerChatClient, CompactionTriggers.TokensExceed(0x500)),

    // 3. Aggressive: keep only the last 4 user turns
    new SlidingWindowCompactionStrategy(CompactionTriggers.TurnsExceed(4)),

    // 4. Emergency: hard token-budget backstop
    new TruncationCompactionStrategy(CompactionTriggers.TokensExceed(0x8000)));

AIAgent agent =
    agentChatClient
        .AsBuilder()
        .UseAIContextProviders(new CompactionProvider(pipeline))
        .BuildAIAgent(options);
```

### `ChatReducerCompactionStrategy` — Adapter

Bridges any `Microsoft.Extensions.AI.IChatReducer` implementation into the compaction pipeline, making it easy to reuse existing reduction logic.

## Complete Pipeline Example

The [`Agent_Step18_CompactionPipeline`](../dotnet/samples/02-agents/Agents/Agent_Step18_CompactionPipeline/Program.cs) sample demonstrates a shopping assistant with all four strategies wired into a `PipelineCompactionStrategy`. It runs a seven-turn conversation with tool calls and shows how the message count is kept bounded across turns:

```csharp
IChatClient agentChatClient = openAIClient.GetChatClient(deploymentName).AsIChatClient();
IChatClient summarizerChatClient = openAIClient.GetChatClient(deploymentName).AsIChatClient();

PipelineCompactionStrategy compactionPipeline =
    new(new ToolResultCompactionStrategy(CompactionTriggers.MessagesExceed(7)),
        new SummarizationCompactionStrategy(summarizerChatClient, CompactionTriggers.TokensExceed(0x500)),
        new SlidingWindowCompactionStrategy(CompactionTriggers.TurnsExceed(4)),
        new TruncationCompactionStrategy(CompactionTriggers.TokensExceed(0x8000)));

AIAgent agent =
    agentChatClient
        .AsBuilder()
        .UseAIContextProviders(new CompactionProvider(compactionPipeline))
        .BuildAIAgent(
            new ChatClientAgentOptions
            {
                Name = "ShoppingAssistant",
                ChatOptions = new()
                {
                    Instructions = "You are a helpful shopping assistant...",
                    Tools = [AIFunctionFactory.Create(LookupPrice)]
                }
            });
```

## Choosing a Strategy

| Strategy | Context loss | Speed | Best for |
|---|---|---|---|
| `ToolResultCompactionStrategy` | Minimal | Fast | Tool-heavy agents |
| `SummarizationCompactionStrategy` | Low (semantic) | Slow (LLM call) | Long sessions with key facts |
| `SlidingWindowCompactionStrategy` | Moderate | Fast | Bounded-turn conversations |
| `TruncationCompactionStrategy` | High | Fast | Emergency backstop |
| `PipelineCompactionStrategy` | Graduated | Combined | Production agents |

For most production agents, a `PipelineCompactionStrategy` ordering strategies from least to most aggressive — with `TruncationCompactionStrategy` as the final backstop — provides the best balance of context preservation and robustness against runaway context growth.
