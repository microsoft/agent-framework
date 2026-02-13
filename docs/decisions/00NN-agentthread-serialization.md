---
# These are optional elements. Feel free to remove any of them.
status: proposed
contact: westey-m
date: 2026-01-02
deciders: sergeymenshykh, markwallace, rbarreto, dmytrostruk, westey-m, eavanvalkenburg, stephentoub
consulted: 
informed:
---

# AgentThread serialization

## Context and Problem Statement

Serializing AgentThreads today is done by calling a Serialize method on the AgentThread instance and deserialization
is done via a Deserialize method on the AIAgent instance.

This approach has some drawbacks:

1. It requires each AgentThread implementation to implement its own serialization logic. This can lead to inconsistencies and errors if not done correctly.
1. It means that only one serialization format can be supported at a time. If we want to support multiple formats (e.g., JSON, XML, binary), we would need to implement separate serialization logic for each format.
1. It is not possible to serialize and deserialize lists of AgentThreads, since each need to be handled individually.
1. Users may not realise that they need to call these specific methods to serialize/deserialize AgentThreads.

The reason why this approach was chosen initially is that AgentThreads may have behaviors that are attached to them and only the agent knows what behaviors to attach.
These behaviors also have their own state that are attached to the AgentThread.
The behaviors may have references to SDKs or other resources that cannot be created via standard deserialization mechanisms.
E.g. an AgentThread may have a custom ChatMessageStore that knows how to store chat history in a specific storage backend and has a reference to the SDK client for that backend.
When deserializing the AgentThread, we need to make sure that the ChatMessageStore is created with the correct SDK client.

## Decision Drivers

- A. Ability to continue to support custom behaviors.
- B. Ability to serialize and deserialize AgentThreads via standard serialization mechanisms, e.g. JsonSerializer.Serialize and JsonSerializer.Deserialize.
- C. Ability for the caller to access custom behaviors.

## Considered Options

- Option 1: Separate state from behavior, serialize state only and re-attach behavior on first usage
- Option 2: Separate state from behavior, and only have state on AgentThread
- Option 3: Keep the current approach of custom Serialize/Deserialize methods

### Option 1: Separate state from behavior, serialize state only and re-attach behavior on first usage

Decision Drivers satisified: A, B and C (C only partially)

Have separate properties on the AgentThread for state and behavior and mark the behavior property with [JsonIgnore].
After deserializing the AgentThread, the behavior is null and when the AgentThread is first used by the Agent, the behavior is created and attached to the AgentThread.

This requires polymorphic deserialization to be supported, so that the correct AgentThread subclass and the correct behavior state is created during deserialization.
Since the implementations for AgentThreads and their behaviors are not all known at compile time, we need a way to register custom AgentThread types and their corresponding behavior types for serialization with System.Text.Json on our JsonUtilities helpers.

A drawback of this approach is that the AgentThread is in an incomplete state after deserialization until it is first used,
so if a user was to call `GetService<MyBehavior>()` on the AgentThread before it is used by the Agent, it would return null.

Behaviors like ChatMessageStore and AIContextProviders would need to change to support taking state as input and exposing state publicly.

```csharp
public class ChatClientAgentThread
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

1. If an AgentThread is provided, check if the ChatMessageStore property is null.
1. If it is, check if the ChatMessageStoreState property is null.
    1. If ChatMessageStoreState is null, check if there is a provided ChatMessageStoreFactory.
        1. If there is, call it with a ChatMessageStoreFactoryContext containing null State to create a default ChatMessageStore behavior, and update the AgentThread with the created behavior and its state.
        2. If there is not, create a default InMemoryChatMessageStore behavior, and update the AgentThread with the created behavior and its state.
    1. If ChatMessageStoreState is not null, check if there is a provided ChatMessageStoreFactory.
        1. If there is, call it with a ChatMessageStoreFactoryContext containing the State to create a ChatMessageStore behavior based on the state.
        2. If there is not, create an InMemoryChatMessageStore behavior based on the State.

### Option 2: Separate state from behavior, and only have state on AgentThread

Decision Drivers satisified: A, B and C (C if we introduce an agent based GetBehavior method).

This is similar to Option 1 but instead of having a behavior property on the AgentThread, we only have state properties on the AgentThread.
Each time the AgentThread is used by the Agent, the behavior is created based on the stored state properties.

This means that users are unable to access the behavior from the AgentThread, e.g. via `AgentThread.GetService<TBehavior>()`.

However, we could potentially introduce a method on the Agent to get the behavior via the Agent, e.g. `AIAgent.GetBehavior<TBehavior>(AgentThread thread)`. This would require multiple copies of a behavior to be able to operate on a single behavior state, since it would not be possible to avoid having two behavior instances for the same behavior at the same time.

```csharp
public class ChatClientAgentThread
{
    ...
    public ChatMessageStoreState ChatMessageStoreState { get; }
    ...
}
```

### Option 3: Keep the current approach of custom Serialize/Deserialize methods

Decision Drivers satisified: A and C

This option keeps the current approach of having custom Serialize/Deserialize methods on the AgentThread and AIAgent.

## Decision Outcome

TBD
