# Using a Compaction Pipeline with an Agent

This sample demonstrates how to use a `ChatHistoryCompactionPipeline` as the `ChatReducer` for an agent's in-memory chat history. The pipeline chains multiple compaction strategies from least aggressive to most aggressive, keeping the conversation history within configurable token and turn-count budgets while preserving the most important context.

## What this sample demonstrates

- Building a `ChatHistoryCompactionPipeline` from multiple ordered `ChatHistoryCompactionStrategy` instances
- Using `ToolResultCompactionStrategy` to collapse old tool-call groups into concise summaries
- Using `SummarizationCompactionStrategy` to LLM-compress older conversation spans into a single summary message
- Using `SlidingWindowCompactionStrategy` to keep only the most recent N user turns
- Using `TruncationCompactionStrategy` as an emergency backstop to enforce a token budget
- Attaching the pipeline as the `ChatReducer` on `InMemoryChatHistoryProvider`
- Observing chat history size shrink across a multi-turn conversation with tool calls

## Key concepts

### Compaction strategies

Each strategy in the pipeline is evaluated in order. A strategy runs only when its trigger condition is met (e.g., token count exceeds a threshold), so earlier, gentler strategies can bring the conversation within limits before the more aggressive ones are reached.

| Strategy | Aggressiveness | Trigger | Behavior |
|---|---|---|---|
| `ToolResultCompactionStrategy` | Gentle | Token count exceeds `maxTokens` and tool calls exist | Collapses old assistant–tool-call groups into a single `[Tool calls: ...]` summary message |
| `SummarizationCompactionStrategy` | Moderate | Token count exceeds `maxTokens` | Uses an LLM to produce a concise summary of older conversation spans, replacing them with a single assistant message |
| `SlidingWindowCompactionStrategy` | Aggressive | User turn count exceeds `maxTurns` | Keeps only the most recent N user turns and their responses; always preserves system messages |
| `TruncationCompactionStrategy` | Emergency backstop | Token count exceeds `maxTokens` | Drops the oldest non-system message groups until the token budget is satisfied |

### Factory method

Rather than building the pipeline manually, you can use the `ChatHistoryCompactionPipeline.Create` factory method for common configurations:

```csharp
// Aggressive: ToolResult → Summarization → SlidingWindow → Truncation
ChatHistoryCompactionPipeline pipeline = ChatHistoryCompactionPipeline.Create(
    ChatHistoryCompactionPipeline.Approach.Aggressive,
    ChatHistoryCompactionPipeline.Size.Compact,
    summarizerChatClient);

// Balanced: ToolResult → SlidingWindow (no LLM required)
ChatHistoryCompactionPipeline pipeline = ChatHistoryCompactionPipeline.Create(
    ChatHistoryCompactionPipeline.Approach.Balanced,
    ChatHistoryCompactionPipeline.Size.Adequate,
    summarizerChatClient);

// Gentle: ToolResult only
ChatHistoryCompactionPipeline pipeline = ChatHistoryCompactionPipeline.Create(
    ChatHistoryCompactionPipeline.Approach.Gentle,
    ChatHistoryCompactionPipeline.Size.Accomodating,
    summarizerChatClient);
```

### Attaching the pipeline to an agent

Pass the pipeline as the `ChatReducer` property on `InMemoryChatHistoryProviderOptions`:

```csharp
AIAgent agent = agentChatClient.AsAIAgent(
    new ChatClientAgentOptions
    {
        ChatHistoryProvider = new InMemoryChatHistoryProvider(new() { ChatReducer = compactionPipeline }),
    });
```

## Prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 10 SDK or later
- Azure OpenAI service endpoint and a chat model deployment (e.g., `gpt-4o-mini`)
- Azure CLI installed and authenticated (for Azure credential authentication)
- User has the `Cognitive Services OpenAI Contributor` role for the Azure OpenAI resource

**Note**: This sample uses Azure OpenAI models. For more information, see [how to deploy Azure OpenAI models with Azure AI Foundry](https://learn.microsoft.com/en-us/azure/ai-foundry/how-to/deploy-models-openai).

**Note**: This sample uses Azure CLI credentials for authentication. Make sure you're logged in with `az login` and have access to the Azure OpenAI resource. For more information, see the [Azure CLI documentation](https://learn.microsoft.com/cli/azure/authenticate-azure-cli-interactively).

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

The sample creates a shopping assistant agent that can look up product prices via a tool. It then runs a seven-turn conversation that exercises the compaction pipeline:

1. The agent answers each price query by calling the `LookupPrice` tool
2. After each turn, the current chat history size is printed
3. As the conversation grows, the pipeline triggers — first collapsing tool-call groups, then summarizing or sliding the window — keeping the history count low
4. The agent continues to answer questions coherently even after earlier turns have been compacted

The printed history counts will decrease at the turns where compaction fires, illustrating how the pipeline keeps the conversation within its configured budgets.
