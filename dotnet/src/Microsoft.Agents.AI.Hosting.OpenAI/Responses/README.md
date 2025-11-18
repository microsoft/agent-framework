# Problem: OpenAI Responses and conversation management

## Prerequisites

1) We are talking about the case of **Hosting** an agent. **Hosting** here means that agent is registered in the DI of aspnetcore app, it is resolved per e.g. HTTP request to the server and invokes the agent under the hood. It can be exposed via any protocol we can consider implementing.

2) Imagine user is using conversations feature of the OpenAI Responses protocol, meaning they are communicating with the specific `conversation` id. That means that agent invocation has to obtain the context of specific conversation (like load messages / metadata / whatever).

OpenAI Responses protocol has the following requirements (for the straightforward implementation):
- persist conversation and its messages
- load conversation by its id
- load its messages by id
- save conversation and messages by id

_Note: we are not considering anything crazy here, like forking the conversation and etc. very basic stuff_

## Goal

[HostedAgentResponseExecutor](./HostedAgentResponseExecutor.cs) processes the input in the OpenAI Responses format (see `ExecuteAsync`). It has `AgentInvocationContext` context (the metadata about the call including responseId and conversationId) and `CreateResponse` request having the actual request data.

There are 2 abstractions to work out the conversation persistently today: `AgentThreadStore` and `ChatMessageStore` (taking into the account that we have `ChatClientAgent` - the most popular variation of the agent).

We want to use the existing API to achieve a way to support given requirement for implementing OpenAI Responses protocol.

## Implementation: What we have today

Here what we have today:
```csharp
string agentName = GetAgentName(request)!;
string conversationId = context.ConversationId;

var agent = this._serviceProvider.GetRequiredKeyedService<AIAgent>(agentName);
var chatOptions = new ChatOptions
{
    Temperature = (float?)request.Temperature,
    TopP = (float?)request.TopP,
    MaxOutputTokens = request.MaxOutputTokens,
    Instructions = request.Instructions,
    ModelId = request.Model,
};
var options = new ChatClientAgentRunOptions(chatOptions);
var messages = new List<ChatMessage>();

foreach (var inputMessage in request.Input.GetInputMessages())
{
    messages.Add(inputMessage.ToChatMessage());
}

// agent invocation
await foreach (var streamingEvent in agent.RunStreamingAsync(messages, thread, options: options, cancellationToken: cancellationToken)
    .ToStreamingResponseAsync(request, context, cancellationToken).ConfigureAwait(false))
{
    yield return streamingEvent;
}
```

The code does the following:
1) resolves the agent based on request data. For example we now will be using agent "pirate"
2) Fills the messages collection, prepares options to run
3) invokes the agent via `RunStreamingAsync`

Problems:
1) We are not having any code which restores the `AgentThread` here
2) We do not save messages anywhere either

This code is straightforward, but does not achieve what we want

## Implementation 1: Use `AgentThreadStore`

Lets only use `AgentThreadStore` for a second. Now we will be resolving the `AgentThreadStore` (consider it is attached to the agent, or uses default store).

Firstly, registration is quite easy. `.WithInMemoryThreadStore()` here basically registers the implementaiton of `AgentThreadStore` in the DI, which can be resolved later.
```csharp
var pirateAgentBuilder = builder.AddAIAgent(
    "pirate", instructions: "You are a pirate. Speak like a pirate", chatClientServiceKey: "chat-model")
    .WithInMemoryThreadStore();
```

The code part is still pretty easy:
```csharp
var agent = this._serviceProvider.GetRequiredKeyedService<AIAgent>(agentName);
var threadStore = this._serviceProvider.GetKeyedService<AgentThreadStore>(agent.Name);

AgentThread thread = !context.IsNewConversation && threadStore is not null
    ? await threadStore.GetThreadAsync(agent, conversationId, cancellationToken).ConfigureAwait(false)
    : agent.GetNewThread();

// agent invocation
await foreach (var streamingEvent in agent.RunStreamingAsync(messages, thread, options: options, cancellationToken: cancellationToken)
    .ToStreamingResponseAsync(request, context, cancellationToken).ConfigureAwait(false))
{
    yield return streamingEvent;
}

if (threadStore is not null && thread is not null)
{
    await threadStore.SaveThreadAsync(agent, conversationId, thread, cancellationToken).ConfigureAwait(false);
}
```

Now the difference is that we construct a thread (via known `agent.GetNewThread()` or `agent.DeserializeThread(JsonElement)`) and pass it in the agent. Then we save the thread using `thread.Serialize()`.

Benefits:
1) we solved the problem that we pass the "conversation" messages to the invocation - now agent has some context

Problems:
1) Whatever we restore and save is in an unknown format - basically `JsonElement`. We cannot restore conversationId , responseId, any metadata or any messages from the `thread` variable that was updated during `agent.RunStreamingAsync()`
2) Additionally to having some kind of store used in this sample (`AgentThreadStore`) we still need something else. Ideally it should be a single store solving the problems of restoring/saving conversation AND having an ability to lookup into it based on the conversation id.

## Implementation 2: Use `ChatMessageStore`

Building `AIAgent` and registering is a bit different but follows same principle: pass in the `ChatMessageStoreFactory`:
```csharp
var testAgent = builder.AddAIAgent("problemCheck", (sp, name) =>
{
    var chatClient = sp.GetRequiredKeyedService<IChatClient>("chat-model");
    return new ChatClientAgent(chatClient, options: new()
    {
        ChatMessageStoreFactory = ctx => new ConversationAgentThreadStore(ctx),
        Name = "problemCheck",
        Instructions = "You need to state a problem and fix it!"
    });
});
```

And we dont need any changes to the initial implementation: this store is already inside of the agent, so it will be used by the internals. The interesting part is how `ConversationAgentThreadStore` is implemented:
```csharp
public class ConversationAgentThreadStore : ChatMessageStore
{
    private readonly IConversationStorage _conversationStorage;
    private readonly ChatMessageStoreFactoryContext _ctx;

    public ConversationAgentThreadStore(ChatMessageStoreFactoryContext ctx)
        : this(ctx, new InMemoryConversationStorage())
    {
    }

    internal ConversationAgentThreadStore(ChatMessageStoreFactoryContext ctx, IConversationStorage conversationStorage)
    {
        this._conversationStorage = conversationStorage;
        this._ctx = ctx;
    }

    public override Task AddMessagesAsync(IEnumerable<ChatMessage> messages, CancellationToken cancellationToken = default)
    {
        // missing responseId, conversationId

        var idGenerator = new IdGenerator(responseId: ..., conversationId: ...);
        var items = messages.SelectMany(x => x.ToItemResource(idGenerator, OpenAIHostingJsonUtilities.DefaultOptions));
        return this._conversationStorage.AddItemsAsync(conversationId: ..., items, cancellationToken);
    }

    public override async Task<IEnumerable<ChatMessage>> GetMessagesAsync(CancellationToken cancellationToken = default)
    {
        // missing conversationId

        ListResponse<ItemResource> items = await this._conversationStorage.ListItemsAsync(conversationId: ..., cancellationToken: cancellationToken).ConfigureAwait(false);
        return items.Data.Select(x => x.ToChatMessage());
    }

    public override JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
    {
        // no conversationId. What can be even done here?
        return JsonDocument.Parse("{}").RootElement;
    }
}
```

The API is basically - `Get` or `Add` messages and `Serialize`. Since we have a singleton agent per app, and it could be used per multiple users at the same time, and it has a single messageStore here for every one of request handlers.

However, `AddMessagesAsync(IEnumerable<ChatMessage>, CancellationToken)` or `GetMessagesAsync(CancellationToken)` both do not have any context passed here - we do not know the `responseId` or `conversationId` which is required by the protocol and by a matching protocol features interface `IConversationStorage` (an explicit implementation, not a public API).

Moreover, `Serialize` only allows to store the collection of `ChatMessage` - otherwise no metadata can be pushed into the callsite of the `ChatMessageStore` implementation (in this case `ConversationAgentThreadStore`).

Benefits:
1) does not build a separate layer with thread usage opposed to #2
2) has a visibility into `ChatMessage` which is quite nice abstraction to give to the user to handle

Problems:
1) Does not have **any context** in the API, which dissallowes lookup into `ChatOptions`, `AgentThread` or the `Agent` itself. In this case misses the necessary `conversationId` and `responseId`.

## Conclusions

Both `AgentThreadStore` and `ChatMessageStore` are unfitting API for the very basic OpenAI Responses implementation, and the very least thing to do is to use both + make changes to `ChatMessageStore` to have some context of the invocation passed inside it.

That means API has to be redesigned to make it more extensible and convenient. The important bit is that today there are several abstractions:
1) AIAgent
2) AgentThread
3) AgentRunOptions
4) ChatMessageStore

which are all interconnected in such a way, that **only a single combination of all of them** can work together. That is an antonym of "abstraction" - a specific implementation fitting the API that can be passed into basically any other component requiring abstract type.