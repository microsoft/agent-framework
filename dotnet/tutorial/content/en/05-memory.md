# Agent Memory

**Sample:** `dotnet/samples/01-get-started/04_memory/`

`AIContextProvider` is MAF's extension point for custom memory. It lets you inject extra context before each LLM call and extract information after each response.

## The Complete Program

```csharp
// Copyright (c) Microsoft. All rights reserved.

// This sample shows how to add a basic custom memory component to an agent.
// The memory component subscribes to all messages added to the conversation and
// extracts the user's name and age if provided.

using System.Text;
using System.Text.Json;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI;
using OpenAI.Chat;
using SampleApp;

var apiKey = Environment.GetEnvironmentVariable("OPENAI_API_KEY")
    ?? throw new InvalidOperationException("OPENAI_API_KEY is not set.");
var model = Environment.GetEnvironmentVariable("OPENAI_MODEL") ?? "gpt-4o-mini";

ChatClient chatClient = new OpenAIClient(apiKey)
    .GetChatClient(model);

// Create the agent and provide a factory to add our custom memory component to
// all sessions created by the agent.
AIAgent agent = chatClient.AsAIAgent(new ChatClientAgentOptions()
{
    ChatOptions = new() { Instructions = "You are a friendly assistant. Always address the user by their name." },
    AIContextProviders = [new UserInfoMemory(chatClient.AsIChatClient())]
});

// Create a new session for the conversation.
AgentSession session = await agent.CreateSessionAsync();

Console.WriteLine(">> Use session with blank memory\n");
Console.WriteLine(await agent.RunAsync("Hello, what is the square root of 9?", session));
Console.WriteLine(await agent.RunAsync("My name is Ruaidhrí", session));
Console.WriteLine(await agent.RunAsync("I am 20 years old", session));

// Serialize the session — includes memory state.
JsonElement sessionElement = await agent.SerializeSessionAsync(session);

Console.WriteLine("\n>> Use deserialized session with previously created memories\n");
var deserializedSession = await agent.DeserializeSessionAsync(sessionElement);
Console.WriteLine(await agent.RunAsync("What is my name and age?", deserializedSession));

Console.WriteLine("\n>> Read memories using memory component\n");
var userInfo = agent.GetService<UserInfoMemory>()?.GetUserInfo(deserializedSession);
Console.WriteLine($"MEMORY - User Name: {userInfo?.UserName}");
Console.WriteLine($"MEMORY - User Age: {userInfo?.UserAge}");

Console.WriteLine("\n>> Use new session with previously created memories\n");
var newSession = await agent.CreateSessionAsync();
if (userInfo is not null && agent.GetService<UserInfoMemory>() is UserInfoMemory newSessionMemory)
{
    newSessionMemory.SetUserInfo(newSession, userInfo);
}
Console.WriteLine(await agent.RunAsync("What is my name and age?", newSession));
```

## The `UserInfoMemory` Component

```csharp
internal sealed class UserInfoMemory : AIContextProvider
{
    private readonly ProviderSessionState<UserInfo> _sessionState;
    private readonly IChatClient _chatClient;

    public UserInfoMemory(IChatClient chatClient, Func<AgentSession?, UserInfo>? stateInitializer = null)
    {
        this._sessionState = new ProviderSessionState<UserInfo>(
            stateInitializer ?? (_ => new UserInfo()),
            this.GetType().Name);
        this._chatClient = chatClient;
    }

    public override IReadOnlyList<string> StateKeys => [this._sessionState.StateKey];

    public UserInfo GetUserInfo(AgentSession session)
        => this._sessionState.GetOrInitializeState(session);

    public void SetUserInfo(AgentSession session, UserInfo userInfo)
        => this._sessionState.SaveState(session, userInfo);

    // Called AFTER each LLM response — extract and store information
    protected override async ValueTask StoreAIContextAsync(InvokedContext context, CancellationToken cancellationToken = default)
    {
        var userInfo = this._sessionState.GetOrInitializeState(context.Session);

        if ((userInfo.UserName is null || userInfo.UserAge is null)
            && context.RequestMessages.Any(x => x.Role == ChatRole.User))
        {
            var result = await this._chatClient.GetResponseAsync<UserInfo>(
                context.RequestMessages,
                new ChatOptions()
                {
                    Instructions = "Extract the user's name and age from the message if present. If not present return nulls."
                },
                cancellationToken: cancellationToken);

            userInfo.UserName ??= result.Result.UserName;
            userInfo.UserAge ??= result.Result.UserAge;
        }

        this._sessionState.SaveState(context.Session, userInfo);
    }

    // Called BEFORE each LLM request — inject context into the prompt
    protected override ValueTask<AIContext> ProvideAIContextAsync(InvokingContext context, CancellationToken cancellationToken = default)
    {
        var userInfo = this._sessionState.GetOrInitializeState(context.Session);
        StringBuilder instructions = new();

        instructions
            .AppendLine(userInfo.UserName is null
                ? "Ask the user for their name and politely decline to answer any questions until they provide it."
                : $"The user's name is {userInfo.UserName}.")
            .AppendLine(userInfo.UserAge is null
                ? "Ask the user for their age and politely decline to answer any questions until they provide it."
                : $"The user's age is {userInfo.UserAge}.");

        return new ValueTask<AIContext>(new AIContext { Instructions = instructions.ToString() });
    }
}

internal sealed class UserInfo
{
    public string? UserName { get; set; }
    public int? UserAge { get; set; }
}
```

## How `AIContextProvider` Works

Two hooks run on every agent invocation:

```
User message arrives
       ↓
ProvideAIContextAsync()  ← inject extra instructions / retrieved facts
       ↓
LLM request sent
       ↓
LLM response received
       ↓
StoreAIContextAsync()    ← extract and persist information from the exchange
       ↓
Response returned to caller
```

### `ProvideAIContextAsync`

Runs before the LLM call. Return an `AIContext` with extra `Instructions` to prepend to the system prompt. Use this for:

- Injecting retrieved documents (RAG)
- Adding user profile facts
- Providing current time/date

### `StoreAIContextAsync`

Runs after the LLM response. Use `context.RequestMessages` to inspect what was said. Use this for:

- Extracting entities (names, dates, preferences)
- Updating user profiles
- Logging or auditing

## Session-Scoped State

`ProviderSessionState<T>` stores data per-session inside the session's `StateBag`. This means the state travels with the session when serialized:

```csharp
// State is included in serialization automatically
JsonElement saved = await agent.SerializeSessionAsync(session);
AgentSession restored = await agent.DeserializeSessionAsync(saved);
// ← UserInfoMemory state is fully restored
```

## Transferring Memory to a New Session

```csharp
var newSession = await agent.CreateSessionAsync();
if (userInfo is not null && agent.GetService<UserInfoMemory>() is UserInfoMemory mem)
{
    mem.SetUserInfo(newSession, userInfo);
}
```

This lets you start a fresh conversation (no message history) but carry over remembered facts.

## Running the Sample

```bash
cd dotnet/samples/01-get-started/04_memory
dotnet run
```

## Key Takeaways

- Subclass `AIContextProvider` to build custom memory
- `ProvideAIContextAsync` — inject context before LLM call
- `StoreAIContextAsync` — extract state after LLM response
- `ProviderSessionState<T>` — per-session storage that serializes automatically
- `agent.GetService<T>()` — retrieve a registered provider from outside the agent
