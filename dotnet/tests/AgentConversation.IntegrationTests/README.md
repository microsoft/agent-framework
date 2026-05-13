# AgentConversation Integration Test Harness

The `AgentConversation.IntegrationTests` project provides a **reusable test harness** for validating conversation dynamics in long-running, multi-agent scenarios that involve tool use. Instead of rebuilding a large conversation context in every test run, the harness allows you to:

1. **Capture** a representative conversation context once (by driving a real conversation with your AI agents).
2. **Serialize** that context to a JSON file and commit it alongside your tests.
3. **Restore** the saved context in each test run.
4. **Solicit** one or more agent responses from the restored context.
5. **Validate** each response and compare before/after metrics.

---

## Key Abstractions

| Type | Role |
|------|------|
| `IConversationTestCase` | Defines a test case: agents, initial messages, ordered steps, and a method to automate context creation. |
| `IConversationTestSystem` | System-specific plugin: how to **create agents** and how to apply **context compaction** (both vary per AI backend). |
| `ConversationAgentDefinition` | Describes a participating agent — name, instructions, and optional tools. |
| `ConversationStep` | One step in the conversation: which agent to invoke, an optional input message, and an optional validation delegate. |
| `ConversationMetrics` | A snapshot of conversation context size — message count and serialized byte size. |
| `ConversationMetricsReport` | A before/after `ConversationMetrics` pair with delta helpers for reporting. |
| `ConversationContextSerializer` | Serializes and deserializes `IList<ChatMessage>` to/from JSON strings or files. |
| `ConversationHarness` | The core runner that ties everything together. |
| `ConversationHarnessTests<TSystem>` | Abstract xunit base class that subclasses inherit to get the `RunAllTestCasesAsync` test. |

---

## How It Works

### 1. Implement `IConversationTestSystem`

Provide an implementation that knows how to create agents for your target AI backend and optionally compact messages:

```csharp
public sealed class OpenAIConversationTestSystem : IConversationTestSystem
{
    public Task<AIAgent> CreateAgentAsync(ConversationAgentDefinition definition, CancellationToken ct = default)
    {
        var chatClient = new OpenAIClient(apiKey)
            .GetChatClient("gpt-4o")
            .AsIChatClient();

        AIAgent agent = new ChatClientAgent(chatClient, options: new()
        {
            Name = definition.Name,
            ChatOptions = new() { Instructions = definition.Instructions, Tools = definition.Tools }
        });

        return Task.FromResult(agent);
    }

    public Task<IList<ChatMessage>?> CompactAsync(IList<ChatMessage> messages, CancellationToken ct = default)
    {
        // Return null for no compaction, or apply an IChatReducer here.
        return Task.FromResult<IList<ChatMessage>?>(null);
    }
}
```

### 2. Implement `IConversationTestCase`

Define the agents involved, the initial context to restore, and the steps to execute:

```csharp
public sealed class MyConversationTestCase : IConversationTestCase
{
    public string Name => "MyConversation";

    public IReadOnlyDictionary<string, ConversationAgentDefinition> AgentDefinitions { get; } =
        new Dictionary<string, ConversationAgentDefinition>
        {
            ["Assistant"] = new() { Name = "Assistant", Instructions = "You are a helpful assistant." }
        };

    // Load the saved context from a JSON fixture file.
    public IList<ChatMessage> GetInitialMessages() =>
        ConversationContextSerializer.LoadFromFile("fixtures/my-conversation.context.json");

    public IReadOnlyList<ConversationStep> Steps { get; } =
    [
        new ConversationStep
        {
            AgentName = "Assistant",
            Input = new ChatMessage(ChatRole.User, "Summarize our conversation so far."),
            Validate = (response, metrics) =>
            {
                Assert.NotEmpty(response.Text);
                Assert.True(metrics.After.MessageCount > metrics.Before.MessageCount);
            }
        }
    ];

    // Called once to generate the fixture file — not during normal CI runs.
    public async Task<IList<ChatMessage>> CreateInitialContextAsync(
        IReadOnlyDictionary<string, AIAgent> agents, CancellationToken ct = default)
    {
        var agent = agents["Assistant"];
        var session = await agent.CreateSessionAsync(ct);

        // Drive a rich, representative conversation to build up the context.
        await agent.RunAsync(new ChatMessage(ChatRole.User, "Tell me about the weather."), session, cancellationToken: ct);
        await agent.RunAsync(new ChatMessage(ChatRole.User, "What about tomorrow?"), session, cancellationToken: ct);
        // ... more turns ...

        var provider = agent.GetService<InMemoryChatHistoryProvider>()!;
        return provider.GetMessages(session);
    }
}
```

### 3. Derive from `ConversationHarnessTests<TSystem>`

Wire the system and test cases into a concrete test class:

```csharp
public class MyConversationTests(ITestOutputHelper output)
    : ConversationHarnessTests<OpenAIConversationTestSystem>(output)
{
    protected override OpenAIConversationTestSystem CreateTestSystem() => new();

    protected override IEnumerable<IConversationTestCase> GetTestCases() =>
    [
        new MyConversationTestCase(),
    ];
}
```

The inherited `RunAllTestCasesAsync` test method will automatically run all cases and log the before/after metrics to the xunit test output.

---

## Generating Initial Context Fixtures

The context fixture files need to be generated once and committed to the repository. Run the inherited `SerializeAllInitialContextsAsync` test to produce them:

```bash
dotnet test --filter "FullyQualifiedName~SerializeAllInitialContexts"
```

This test is **skipped during normal CI runs** to avoid expensive AI calls. After generating the files, commit them alongside your test code so that all subsequent runs can restore the context without calling the AI service again.

---

## Metrics Reporting

After each test case runs, a `ConversationMetricsReport` is logged. It captures:

- **`Before`** — message count and serialized byte size of the initial context.
- **`After`** — message count and byte size after all steps have executed.
- **`MessageCountDelta`** / **`SizeDeltaBytes`** — the change between before and after.

Example output:

```
[MyConversation] Before=[Messages=12, Size=4096B] After=[Messages=14, Size=4712B] Delta=[Messages=+2, Size=+616B]
```

---

## Example

See [`Microsoft.Agents.AI.Abstractions.IntegrationTests`](../Microsoft.Agents.AI.Abstractions.IntegrationTests) for a self-contained working example that uses an in-memory mock `IChatClient` so it runs without live AI credentials.
