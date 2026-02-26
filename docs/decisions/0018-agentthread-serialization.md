---
# These are optional elements. Feel free to remove any of them.
status: accepted
contact: westey-m
date: 2026-02-25
deciders: sergeymenshykh, markwallace, rbarreto, dmytrostruk, westey-m, eavanvalkenburg, stephentoub
consulted: 
informed:
---

# AgentSession serialization

## Context and Problem Statement

Serializing AgentSessions is done today by calling SerializeSession on the AIAgent instance and deserialization
is done via the DeserializeSession method on the AIAgent instance.

This approach has some drawbacks:

1. It requires each AgentSession implementation to implement its own serialization logic. This can lead to inconsistencies and errors if not done correctly.
1. It means that only one serialization format can be supported at a time. If we want to support multiple formats (e.g., JSON, XML, binary), we would need to implement separate serialization logic for each format.
1. It is not possible to serialize and deserialize lists of AgentSessions, since each need to be handled individually.
1. Users may not realise that they need to call these specific methods to serialize/deserialize AgentSessions.

The reason why this approach was chosen initially is that AgentSessions may have behaviors that are attached to them and only the agent knows what behaviors to attach.
These behaviors also have their own state that are attached to the AgentSession.
The behaviors may have references to SDKs or other resources that cannot be created via standard deserialization mechanisms.
E.g. an AgentSession may have a custom ChatMessageStore that knows how to store chat history in a specific storage backend and has a reference to the SDK client for that backend.
When deserializing the AgentSession, we need to make sure that the ChatMessageStore is created with the correct SDK client.

## Decision Drivers

- A. Ability to continue to support custom behaviors (AIContextProviders / ChatHistoryProviders).
- B. Ability to serialize and deserialize AgentSessions via standard serialization mechanisms, e.g. JsonSerializer.Serialize and JsonSerializer.Deserialize.
- C. Ability for the caller to access custom providers.

## Considered Options

- Option 1: Separate state from behavior, serialize state only and re-attach behavior on first usage
- Option 2: Separate state from behavior, and only have state on AgentSession
- Option 3: Keep the current approach of custom Serialize/Deserialize methods

### Option 1: Separate state from behavior, serialize state only and re-attach behavior on first usage

Decision Drivers satisfied: A, B and C (C only partially)

Have separate properties on the AgentSession for state and behavior and mark the behavior property with [JsonIgnore].
After deserializing the AgentSession, the behavior is null and when the AgentSession is first used by the Agent, the behavior is created and attached to the AgentSession.

This requires polymorphic deserialization to be supported, so that the correct AgentSession subclass and the correct behavior state is created during deserialization.
Since the implementations for AgentSessions and their behaviors are not all known at compile time, we need a way to register custom AgentSession types and their corresponding behavior types for serialization with System.Text.Json on our JsonUtilities helpers.

A drawback of this approach is that the AgentSession is in an incomplete state after deserialization until it is first used,
so if a user was to call `GetService<MyBehavior>()` on the AgentSession before it is used by the Agent, it would return null.

Behaviors like ChatMessageStore and AIContextProviders would need to change to support taking state as input and exposing state publicly.

```csharp
public class ChatClientAgentSession
{
    ...
    public ChatMessageStoreState ChatMessageStoreState { get; }
    public ChatMessageStore? ChatMessageStore { get; }
    ...
}

[JsonPolymorphic(TypeDiscriminatorPropertyName = "$type")]
[JsonDerivedType(typeof(InMemoryChatMessageStoreState), nameof(InMemoryChatMessageStoreState))]
public abstract class ChatMessageStoreState
{
}
public class InMemoryChatMessageStoreState : ChatMessageStoreState
{
    public IList<ChatMessage> Messages { get; set; } = [];
}

public abstract class ChatMessageStore<TState>
    where TState : ChatMessageStoreState
{
    ...
    public abstract TState State { get; }
    ...
}

public sealed class InMemoryChatMessageStore : ChatMessageStore<InMemoryChatMessageStoreState>, IList<ChatMessage>
{
    private readonly InMemoryChatMessageStoreState _state;

    public InMemoryChatMessageStore(InMemoryChatMessageStoreState? state)
    {
        this._state = state ?? new InMemoryChatMessageStoreState();
    }

    public override InMemoryChatMessageStoreState State => this._state;

    ...
}
```

ChatClientAgent factories would need to change to support creating behaviors based on state:

```csharp
    public Func<ChatMessageStoreFactoryContext, ChatMessageStore>? ChatMessageStoreFactory { get; set; }

    public class ChatMessageStoreFactoryContext
    {
        public ChatMessageStoreState? State { get; set; }
    }
```

The run behavior of the ChatClientAgent would be as follows:

1. If an AgentSession is provided, check if the ChatMessageStore property is null.
1. If it is, check if the ChatMessageStoreState property is null.
    1. If ChatMessageStoreState is null, check if there is a provided ChatMessageStoreFactory.
        1. If there is, call it with a ChatMessageStoreFactoryContext containing null State to create a default ChatMessageStore behavior, and update the AgentSession with the created behavior and its state.
        2. If there is not, create a default InMemoryChatMessageStore behavior, and update the AgentSession with the created behavior and its state.
    1. If ChatMessageStoreState is not null, check if there is a provided ChatMessageStoreFactory.
        1. If there is, call it with a ChatMessageStoreFactoryContext containing the State to create a ChatMessageStore behavior based on the state.
        2. If there is not, create an InMemoryChatMessageStore behavior based on the State.

### Option 2: Separate state from behavior, and only have state on AgentSession

Decision Drivers satisfied: A, B and C.

This is similar to Option 1 but instead of having a behavior property on the AgentSession, we only have a StateBag property on the AgentSession.
Behaviors really make more sense to live with the agent rather than the Session, but state should live on the session.
When the AgentSession is used by the Agent, the Agent runs the behaviors against the Session, and the behavior stores it's state on the Session StateBag.

This means that users are unable to access the behavior from the AgentSession, e.g. via `AgentSession.GetService<TBehavior>()`.

However, the behaviors can be public properties on the Agent or can be retrieved from the agent via `AIAgent.GetService<MyAIContextProvider>()`.

```csharp
public class AgentSession
{
    ...
    public AgentSessionStateBag StateBag { get; protected set; } = new();
    ...
}
```

### Option 3: Keep the current approach of custom Serialize/Deserialize methods

Decision Drivers satisfied: A and C

This option keeps the current approach of having custom Serialize/Deserialize methods on the AgentSession and AIAgent.

## Decision Outcome

Chosen option:

**Option 2** — separate state from behavior, with only state on the AgentSession — because it satisfies all decision drivers and provides the cleanest separation of concerns. Since not all AgentSession implementations have yet been cleanly separated from their behaviors, AIAgent.SerializeSession and AIAgent.DeserializeSession is kept for the time being, but most session types can be serialized and deserialized directly using JsonSerializer.

### Consequences

- Good, because providers are fully stateless — the same provider instance works correctly across any number of concurrent sessions without risk of state leakage.
- Good, because `AgentSession` can be serialized and deserialized with standard `System.Text.Json` mechanisms, satisfying decision driver B.
- Good, because the generic `StateBag` is extensible — new providers can store arbitrary state without requiring changes to the session class.
- Good, because users can access providers via the agent (e.g. `agent.GetService<InMemoryChatHistoryProvider>()`) satisfying decision driver C.
- Good, because sessions are always in a complete and valid state after deserialization — there is no "incomplete until first use" problem as in Option 1.
- Neutral, because providers cannot be accessed directly from the session; callers must go through the agent. This is a minor usability trade-off but keeps the session focused on state only.
- Bad, because each provider must be disciplined about using `ProviderSessionState<T>` and not storing session-specific data in instance fields. This is a correctness concern for custom provider implementers.
