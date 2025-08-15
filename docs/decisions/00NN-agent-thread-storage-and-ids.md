---
# These are optional elements. Feel free to remove any of them.
status: proposed
contact: westey-m
date: 2025-08-15 # {YYYY-MM-DD when the decision was last updated}
deciders: sergeymenshykh, markwallace-microsoft, rogerbarreto, dmytrostruk, westey-m, eavanvalkenburg, stephentoub, peterychang
consulted: 
informed: 
---

# Agent Thread

## Context and Problem Statement

### Message Storage Location

We need a way to abstract away the different behaviors that different agent threads exhibit, specifically when it comes to message storage.

There are three different messages storage scenarios we need to support:

1. **AgentService**: The messages are stored by the agent/inference service being used by the agent.
2. **InMemory**: The messages are stored in-memory and are transient.
3. **3rdParty**: The messages are stored in a 3rd party storage solution, e.g. Cosmos DB.

With Scenario 1 the storage of messages is built into the underlying service, and the service typically only supports storage of messages it its own storage.

Where services do not have built in storage (1), the caller typically has to provide all chat history on each invocation.
The messages making up this chat history, can be stored either in memory locally or in some 3rd party storage location.
The service is agnostic to where the messages are stored, and any such 3rd party storage needs to be provided by the agent framework.

### Service message storage

Agentic/Inference Services that have built in message storage, typically expose an id that represents the message thread.
We therefore need the ability to store that id, in cases where the agent is using a service with built in storage.

Note that we have multiple possible scenarios for the type and quantity of threads being used by an agent.

- If the agent is a simple ChatClientAgent that agent may have 0 or 1 thread ids for communicating with the underlying service.
- If the agent is a complex custom agent, it may use multiple underlying services with different thread ids.

### InMemory/3rdParty storage

For cases where the Agentic/Inference Service does not have built in message storage, we need to provide support in the agent framework for storage messages elsewhere.

The simplest of these options is **InMemory** storage, where messages are just kept in an object and are transient.
In many cases, this is sufficient for short-lived conversations where the context does not need to be persisted.
Here, the thread object contains all the messages.

There may be other cases where longer-lived conversations require more robust storage solutions, such as a 3rd party database.
The storage may also be provided by a conversation storage service that provides support for chat history reduction.
E.g. messages may be added to the service as they are created, but the service may then do truncation/summarization in the background
to keep the chat history small enough to fit within any required context window.
This means that the agent would want to request the latest chat history from the service before each invocation.

For the 3rd party storage scenario, the thread object needs to capture the id (could be a compound id too, e.g. partitionkey+id) that the messages are stored under.
The thread should also be able to update and query that 3rd party storage solution.

This id used for 3rd party storage should not be confused with any id used for an Agentic/Inference Service's built in storage.
They are mutually exclusive, since if you use Agentic/Inference service provided storage, you cannot provide chat history on each invocation
and 3rd party storage becomes pointless.
Conversely, if the Agentic/Inference service does not provide built in storage, you must provide chat history on each invocation.

It's also important to consider the case where services support both modes, e.g. Responses with store=true or store=false.
If we are using store=false, and storing data in a 3rd party storage solution under an id, we need to ensure that we don't
confuse that id for a Response id, as passing it to the response service will result in an error.
It would not be a valid response id after all.

### Public thread id support

Let's consider a scenario where we have a ChatClientAgent that is hosted in a service and exposed publicly via the A2A protocol.
This agent may be built using Responses (store = true), and therefore have a response id that it needs to communicate with the underlying service.
However, when the agent is accessed via A2A, the thread is represented using an A2A context id.
These two ids have very different behavioral characteristics.
Response ids change with each turn of the conversation, while A2A context ids remain constant for the duration of the conversation.
These two ids therefore cannot be the same.

Let's step through the sequence of events for a thread that already exists:

1. The service is invoked via the A2A protocol with a context id.
2. The A2A context id is used to look up the thread object state from storage.
3. The thread object state is loaded from storage. The state will need to be stored under the context id to ensure it can be retrieved.
4. The thread object contains the the separate response id used to invoke the responses api.
5. The agent uses the response id to communicate with the underlying service.
6. The thread is updated with the new response id from the underlying service, plus the input and output messages for this run.
7. The service returns the response to the caller via the A2A protocol.
8. The service serializes the thread object state and stores it under the context id.

Agents may be exposed via other protocols as well, which may require similar "public" thread ids to the context id of A2A.
Some may even require a response style id change after each invocation.
Similarly to the previous example the internal thread id used to communicate with the service may however be static, making it important to support two separate ids.

### Service Storage support for different services

|Underlying Service|Uses Service Storage|
|---|---|
|Foundry Agents|Y|
|OpenAI Assistants|Y|
|OpenAI Responses (store = true)|Y|
|OpenAI Responses (store = false)|N|
|OpenAI Chat|N|
|All other inference services|N|
|A2A|Y|
|CopilotStudio|Y|
|Custom Agent|Could be either, agent decides|

## Considered Options

### Decision A: Id Management

#### Option 1 - Public Id has concrete property, service thread id is considered implementation detail of Agent and stored in AdditionalProperties

AgentThread has an `Id` property that exposes the thread's public ID.
Any thread id required for communication with the underlying service would be stored in `AdditionalProperties`.

```csharp
public class AgentThread
{
    public string Id { get; set; }
    public Dictionary<string, string> AdditionalProperties { get; set; }
}

new AgentThread()
{
    Id = "thread-1",
    AdditionalProperties = new Dictionary<string, string>
    {
        { "response-id", "r-12345" }
    }
}
```

#### Option 2 - Public Id has concrete property, service thread id has concrete property

AgentThread has an `Id` property that exposes the thread's public ID.
It also has a `ServiceThreadId` property that exposes the thread's ID used for communication with the underlying service.

If the agent is using multiple underlying services with different thread ids, it may need to store thread ids in `AdditionalProperties`.

```csharp
public class AgentThread
{
    public string Id { get; set; }
    public string? ServiceThreadId { get; set; }
    public Dictionary<string, string> AdditionalProperties { get; set; }
}

var singleInternalId = new AgentThread()
{
    Id = "thread-1",
    ServiceThreadId = "r-12345"
}

var multipleInternalIds = new AgentThread()
{
    Id = "thread-1",
    AdditionalProperties = new Dictionary<string, string>
    {
        { "response-id", "r-12345" },
        { "foundry-id", "f-12345" }
    }
}
```

### Decision B: Message Storage

#### Option 1 - Store messages in an IChatMessageStore, defaulted to InMemoryChatMessageStore

The AgentThread class has an optional MessageStore property for storing messages.
The agent cannot use both the MessageStore and an Agentic/InferenceService thread id, so for cases
where an Agentic/InferenceService thread id is available, the MessageStore would be ignored.

When using 3rd party storage, the message store needs to store the messages using
an id. The message store may generate an id for this purpose (on first use), store the messages
using that id, and then keep the id in a property for future use.
When serializing the thread, the message store would need to include the id in its serialized data.
Since the messages store is a child of the thread, its state should be included in the thread's serialized state.

When using In-Memory storage, the messages are simply kept in the InMemoryChatMessageStore in a property.
When serializing the thread, the message store would need to include the messages in its serialized data.

```csharp
// The thread has an optional MessageStore property for storing messages
public class AgentThread
{
    public IChatMessageStore? MessageStore { get; set; }
}

public interface IChatMessageStore
{
    Task<IEnumerable<ChatMessage>> GetMessagesAsync(CancellationToken cancellationToken);
    Task AddMessagesAsync(IReadOnlyCollection<ChatMessage> messages, CancellationToken cancellationToken);
}

// A default InMemoryChatMessageStore implementation is available if no other chat message store is configured.
internal class InMemoryChatMessageStore : IList<ChatMessage>, IChatMessageStore
{
}

public class AIAgent
{
    // The agent is responsible for setting the MessageStore (if needed)
    // when it creates the thread. How it does this is agent specific.
    public virtual AgentThread GetNewThread();
}

// For ChatClientAgent we have a optional factory in options, that developers
// can use to provide new message stores for any threads created by the agent.
// This factory is called by GetNewThread.
public class ChatClientAgentOptions
{
    public Func<IChatMessageStore>? ChatMessageStoreFactory { get; set; } = null;
}
```

#### Option 1.1 - Variation on Option 1: Reuse AgentThread id for messages store

This is a variation of Option 1 where the `Id` of the `AgentThread` is passed to the `MessageStore` when
messages are added or retrieved, so that messages can be stored under this id.

In this case, a 3rd party message store would not need to generate its own ids for messages, as it can use the thread id provided by the `AgentThread`,
however it is still free to generate its own ids.

```csharp
public interface IChatMessageStore
{
    Task<IEnumerable<ChatMessage>> GetMessagesAsync(string threadId, CancellationToken cancellationToken);
    Task AddMessagesAsync(string threadId, IReadOnlyCollection<ChatMessage> messages, CancellationToken cancellationToken);
}
```

#### Option 2 - Store in-memory messages the thread, with an optional IChatMessageStore for 3rd party integrations

The AgentThread class has an optional MessageStore property for storing messages.
The AgentThread also has a ChatHistory property for storing messages in-memory.
Only one of these can be used at a time, and if an Agentic/InferenceService thread id is available,
both the ChatHistory and MessageStore would be ignored.

When serializing the thread, the thread would either include the messages from the ChatHistory, or
whatever state the MessageStore has, including potentially an id under which the MessageStore is storing messages.

```csharp
// The thread has an optional ChatHistory for storing messages in-memory
// and a MessageStore property for storing messages externally if required.
// Only one may be set at a time.
public class AgentThread
{
    public List<ChatMessage>? ChatHistory { get; set; }
    public IChatMessageStore? MessageStore { get; set; }
}

// ChatMessageStore implementation and factory works the same as in option 1.
```

#### Option 2.1 - Variation on Option 2: Reuse AgentThread id for messages store

Same variation as Option 1.1, applied to option 2.
