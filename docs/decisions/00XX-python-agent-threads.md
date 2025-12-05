---
status: Proposed
contact: eavanvalkenburg
date: 2025-11-24
deciders: markwallace-microsoft, dmytrostruk, taochenosu, alliscode, moonbox3
consulted: sergeymenshykh, rbarreto, dmytrostruk, westey-m
---

# Agent Threads Update

## Context and Problem Statement

We are re-looking at the way threads work and what they are.

Threads have the following:
- `AgentThread` - contains: `service_thread_id`, `chat_message_store`, `context_providers`
- In dotnet there are also subclasses used such as `ChatClientAgentThread`, to handle additional logic.
- Threads should be managed by a Agent, not by the user, so creation, serialization, alterations should all be agent methods.
    - In python, we do not have the notion of protected methods, so we cannot prevent users from directly creating `AgentThread` instances, which can lead to confusion, this is why in Python there are no subclasses of `AgentThread`.

### Logical flow of threads
The following diagrams illustrate the logical flow of an agent run with threads in the current implementation.

Current (simplified) state for a AgentThread with a ChatMessageStore in Python:
```mermaid
sequenceDiagram
        participant User
    box Agent Layer
        participant Agent
    end
    box Thread Layer
        participant AgentThread
        participant ChatMessageStore
        participant ContextProvider
    end
    box LLM Layer
        participant ChatClient
    end
        participant LLM

    User->>Agent: run(message, thread)
    Agent->>AgentThread: prepare(message)
    Agent-->>ChatMessageStore: list_messages()
    ChatMessageStore-->>Agent: messages
    Agent->>AgentThread: add_messages(messages)
    AgentThread<<-->>ContextProvider: invoking()
    Agent->>ChatClient: get_response(messages, ...)
    ChatClient<<->>LLM: call(messages, ...)
    ChatClient-->>Agent: response
    Agent->>AgentThread: update_thread(conversation_id | None)
    Agent->>AgentThread: notify_new_messages(response)
    AgentThread->>ChatMessageStore: on_new_messages(response)
    AgentThread->>ContextProvider: invoked()
    Agent-->>User: response
```
And for a thread with a service_thread_id (or `store=True`):
```mermaid
sequenceDiagram
        participant User
    box Agent Layer
        participant Agent
    end
    box Thread Layer
        participant AgentThread
        participant ContextProvider
    end
    box LLM Layer
        participant ChatClient
    end
        participant LLM

    User->>Agent: run(message, thread)
    Agent->>AgentThread: prepare(message)
    AgentThread<<-->>ContextProvider: invoking()
    Agent->>ChatClient: get_response(messages)
    ChatClient<<->>LLM: get_response(messages)
    ChatClient-->>Agent: response
    Agent->>AgentThread: update_thread(conversation_id | None)
    AgentThread->>ContextProvider: invoked()
    Agent-->>User: response
```
There are several issues with the current implementation of threads in the Agent Framework, which we would like to address in this ADR.

### Issue 1: Threads can have different behaviors based on their state
The first issue with threads is that depending on whether the `service_thread_id` is filled we treat it differently from a thread with `chat_message_store` filled, and when neither is filled it is considered uninitialized. Further, depending on the state, certain methods behave differently, such as `on_new_messages`, which is a no-op for threads with a `service_thread_id`, but calls `add_messages` on the `chat_message_store` for threads with that filled. When calling `agent.get_new_thread` it is also unclear what is referred to, a service side thread, a locally stored thread or neither. Finally, when passing in a thread of one type, but also setting the `store` and `conversation_id` parameters when calling `agent.run` might either raise a error, change something or does not work as expected.

### Issue 2: ChatMessageStore usage
The second issue is the usage of `ChatMessageStore` as the way to store messages locally, while it works well, it does not capture a whole thread , so it does not include context provider settings, or a service_thread_id, nor can it be used as a way to store either messages or a service id, leading to the need for a separate class that can store `AgentThread` objects, meaning we either need two abstractions and implementations, one for `ChatMessageStore` and one for `AgentThreadStore`, or we need to complicate the `AgentThread` class further by adding an id and save/load methods. Or people will forego using the ChatMessageStore altogether and just use a AgentThreadStore and the built-in in-memory ChatMessageStore. Giving us two versions of doing similar things: "storing threads", where one works for all thread (AgentThreadStore) and one only for local threads (ChatMessageStore).

### Issue 3: Thread serialization
Because we have both a `ChatMessageStore` object and a `ContextProvider` object inside a thread, it is quite a challenge to serialize and deserialize threads, as both the ChatMessageStore and ContextProviders can have configuration that needs to be serialized as well, including potentially hard to serialize things like clients, for which we would need to add dependency injection, and the logic of how to do that is contained in those classes. This makes it hard to create a standard way of serializing and deserializing threads, as each ChatMessageStore and ContextProvider can have different requirements.

### Issue 4: Thread state inconsistencies
Another issue applies to service side threads and that is that a thread can be updated on the service side without going through a agent. This can lead to inconsistencies between which messages have gone through the agent and it's context providers and which messages have not. For example, if a user adds messages directly to the service side thread, the agent and it's context providers will not be aware of those messages, leading to potential confusion and unexpected behavior.

### Issue 5: Language differences
In .Net threads have protected constructors, and can therefore not be created directly by a user, all interactions (adding messages from a run and (de)serialization) with a thread are also supposed to go through the agent. It is already doubtful if that is a good idea, since it makes adding things like ChatHistoryReducers more difficult, if we keep to that principle, they will have to be part of the agent as well in order to work properly. And in Python, there are no protected methods, classes can be "marked" as private, but that does not prevent users from using them directly.

### Issue 6: Cross-agent threads
Threads are used for certain workflows to support things like group chats, in that case a thread should be shared between multiple agents, but those agents are not necessarily of the same type, or they might be using different chat clients, which might have different support for threads. This makes it problematic to share threads because some might have a preference for a service side thread, but others might use a different service, or have not support for service side threads at all.

## Scenario's
To further clarify both the issues and the solutions, we can look at the scenario's below and ensure we support them, or choose to not support one of them and why.

### Scenario 1: The simple should be simple
A user gets an agent and wants to run a conversation with it, that is continuous, so messages like: "and what about X", referring to something previous discussed should just work.

```python
agent = SomeAgent(...)
thread = agent.get_new_thread()
response1 = agent.run("Tell me about the history of AI.", thread=thread)
response2 = agent.run("And what about in Europe?", thread=thread)
```
Or:
```python
agent = SomeAgent(...)
response1 = agent.run("Tell me about the history of AI.")
response2 = agent.run("And what about in Europe?", thread_id=response1.thread_id)
```

### Scenario 2a: Storing and restoring threads
A user wants to store a thread and restore it later, either in the same session or in a different session.

```python
agent = SomeAgent(...)
thread = agent.get_new_thread()
response1 = agent.run("Tell me about the history of AI.", thread=thread)
# Store thread somewhere
stored_thread_data = agent.serialize_thread(thread)
# Later, restore thread
restored_thread = agent.deserialize_thread(stored_thread_data)
response2 = agent.run("And what about in Europe?", thread=restored_thread)
```

### Scenario 2b: Storing and restoring chat messages
A user wants to store just the chat messages of a thread and restore them later, either in the same session or in a different session.

```python
agent = SomeAgent(ChatMessageStoreFactory=CosmosDBChatMessageStoreFactory())
thread = agent.get_new_thread()
response1 = agent.run("Tell me about the history of AI.", thread=thread)
response2 = agent.run("And what about in Europe?", thread=thread)
```

### Scenario 3: Context Providers
A user wants to use context providers to add context to the conversation, and have that context be stored and restored with the thread, and this should work with any thread type.

```python
agent = SomeAgent(context_providers=[SomeContextProvider(), AnotherContextProvider()])
thread = agent.get_new_thread()
response1 = agent.run("Tell me about the history of AI.", thread=thread)
# Store thread somewhere
stored_thread_data = agent.serialize_thread(thread)
# Later, restore thread
restored_thread = agent.deserialize_thread(stored_thread_data)
response2 = agent.run("And what about in Europe?", thread=restored_thread)
```

Further a context provider should be able to store a few messages (regardless of thread type) as additional context to provide better context, such as the `messages` field of the example below.
```python
class SummaryContextProvider(ContextProvider):

    def __init__(self, chat_client: ChatClient, messages: list[ChatMessage] | None = None, **kwargs: Any):
        self.messages = messages or []
        self.chat_client = chat_client

    async def invoking(self, messages: list[ChatMessage], **kwargs: Any) -> Context:
        context_data = copy(self.messages)
        context_data.extend(messages)
        context_data.append(ChatMessage(role="user", content="Summarize the previous messages in 2 sentences."))
        response = await self.chat_client.get_response(
            messages=context_data,
            store=False,
            conversation_id=None,
        )
        context = Context(messages=response.content)
        return context

    async def invoked(self, request_messages: list[ChatMessage], response_messages: list[ChatMessage], ...) -> dict:
        self.messages.extend(request_messages)
        self.messages.extend(response_messages)
        # Keep only last 10 messages
        self.messages = self.messages[-10:]
```

### Scenario 4: Multi-agent threads with the same agent type
A user wants to share a thread between multiple agents of the same type.

```python
agent1 = SomeAgent(...)
agent2 = SomeAgent(...)

group = GroupChatBuilder().add_participants([agent1, agent2]).build()
group.run("Hello everyone, let's discuss AI.")

```
### Scenario 5: Multi-agent threads with different agent types
A user wants to share a thread between multiple agents of different types.

```python
agent1 = SomeAgentTypeA(...)
agent2 = SomeAgentTypeB(...)
group = GroupChatBuilder().add_participants([agent1, agent2]).build()
group.run("Hello everyone, let's discuss AI.")
```

### Scenario 6: All of the above
A user wants to combine all of the above scenarios.

```python
agent1 = SomeAgentTypeA(context_providers=[SomeContextProvider()])
agent2 = SomeAgentTypeB(chat_message_store_factory=CosmosDBChatMessageStoreFactory()
thread1 = agent1.get_new_thread()
response1 = agent1.run("Tell me about the history of AI.", thread=thread1)
# Store thread somewhere
stored_thread_data = agent1.serialize_thread(thread1)
# Later, restore thread in agent2
restored_thread = agent2.deserialize_thread(stored_thread_data)
response2 = agent2.run("And what about in Europe?", thread=restored_thread)

group = GroupChatBuilder().add_participants([agent1, agent2]).build()
group.run("Hello everyone, let's discuss AI.")
```

## Decision Drivers

- Ease of use: make it easy for users to understand how to use threads, one class, one purpose.
- Clarity: create a single way of storing and restoring threads that is clear and unambiguous.
- Ease of handling: make it easy to work with Threads and store them in a way that is easily serializable.


## Possible enhancements

1. Separate classes for remote thread and local thread, each with their own behaviors and methods.
1. Make Threads fully serializable, including ChatMessageStore and ContextProviders.
    1. Remove `ContextProvider` from the thread itself, replace with `context_data/state` on the thread, which the agent uses to get context from the providers when running in that thread.
    1. Replace `ChatMessageStore` with a list of ChatMessages.
1. Local threads only, adding a abstraction on ChatClient to load a thread by id, so that the local thread can always be synced with the service side thread, and the agent can then run with just the new messages compared to the last known state.
1. Using a Context Provider to handle local message storage and context generation for local threads.
    1. Variant with a special Context Provider that handles local storage and generates a thread id for local threads, so that the agent only deals with thread ids.
    1. Variant with a default Context Provider that can store messages, that can be overridden by other context providers
1. Rename `Thread` for clarity.

### 1. Separate classes for `ServiceThread`/`RemoteThread` and `LocalAgentThread`/`LocalThread`, each with their own behaviors and methods.
This approach would mean:
- Creating two subclasses of AgentThread, one for service threads and one for local threads, both with different attributes and methods. Tentatively called `RemoteThread` and `LocalThread`.
- We would need to add a flag on `ChatClients`, to indicate if they support `remote/service` threads, and we assume that we always support `local` threads.
- All Agents would get two methods, `get_service_thread(thread_id: str | None = None, ...)`/`get_remote_thread(thread_id: str | None = None, ...)` and `get_local_thread(messages: list[ChatMessage] | None = None, ...)`, the former of which might raise an error if the chat client does not support that type of thread, after creation the agent then calls the context_provider(s) to get a `context_data/state` assigned as well.
    - We could then also add a `get_new_thread` method that first tries to create a service thread, and if that fails, creates a local thread, but that might be confusing in the long run, but you could ignore the difference between those threads and just call run with the thread and it just works.
- The `run` methods would take both types of threads, but would raise an error if the thread type is not supported by the chat client.
- If you pass a `LocalThread` to `run`, it would invoke the chat client with `store=False` and `conversation_id=None`, and if you pass a `RemoteThread`, it would invoke the chat client with `store=True` and the `conversation_id` from the thread (if any). And this also means removing the `store` and `conversation_id` parameters from the `run` method at the agent level, as they would be redundant and potentially conflicting.
- Naming is a open question, options are:
    - for the remote threads:
        - `ServiceThread`
        - `RemoteThread`
        - `ServiceSideThread`
        - `HostedThread`
    - for the local threads:
        - `LocalAgentThread`
        - `LocalThread`
        - `ClientSideThread`
    `HostedThread` and `LocalThread` seem the clearest and most concise options and the most pythonic.

### 2. Making Threads fully serializable, including ChatMessageStore and ContextProviders.
This approach would mean:
- Making the thread state only, so instead of a ChatMessageStore, it would be a list of ChatMessages, and instead of ContextProviders, it would be some kind of context state object.

    #### 1. Removing `ChatMessageStore`, use `list[ChatMessage]`, and add a `ThreadStore` abstraction to handle persistence.
    This approach would mean:
    - Removing `ChatMessageStore`, instead a `LocalThread` would have a list of ChatMessages as attribute.

    #### 2. Removing `ContextProvider`, replacing with a field `context_data`/`context_state` or a dict of `context_provider_name/id: context_data/state` on both thread types, which the agent would then use to get the context from the context providers when running in that thread.
    This approach would mean:
    - Moving `ContextProvider` back into Agent, replacing with a field `context_data`/`context_state` or a dict of `context_provider_name/id: context_data/state` on both thread types, which the agent would then use to get the context from the context providers when running in that thread. This makes the thread itself state-only, and the context provider can be stateless and live in the agent.
    - The protocol/interface for ContextProviders would need a slight update, one to return a initial `context_data/state` object, the logic of which is maintained by the provider (whether it matches a app, user or session and what to record in there), and adding that `context_data/state` to the invoked and invoking methods. The `context_data/state` needs to be (de)serializable in a standard way, to make handling the thread easier.

### 4. Local threads only
This approach would mean:
- Adding an abstraction on ChatClient to load a thread by id from the service and cast the messages to our types, so that the local thread can always be synced with the service side thread, and the agent can then run with just the new messages compared to the last known state. This will make supporting cross-agent threads easier.
- The additional latency of reading the service side thread, and the fact that adding a thread reading abstraction to existing ChatClients is a breaking change, means that this option is excluded and will not be further investigated.

### 5. Context Provider to handle local message storage and context generation for local threads.
- The contract of a ChatMessageStore is already quite similar to a Context Provider, so we could create a Context Provider that handles local message storage and context generation for local threads.
- One note is that potentially, something like `Context Manager` would be a more accurate name for such a Context Provider, as it would manage the context (messages) for the thread, but for consistency we will keep using Context Provider here.
- There are two variants to consider here:

    #### 1. Variant with a special Context Provider that handles local storage and generates a thread id for local threads, so that the agent only deals with the service side thread id, and all local context would be handled by the context provider.
    This approach would mean:
    - Creating a default context provider that stores chat messages, when a response has a `response_id/conversation_id`, it updates that id on the thread, and sets a flag on the storage context provider to indicate that messages should not be added as context per run. If the response does not indicate it can store and continue, then the context provider adds the full history (or a reduced version) as context for the next run. This would simplify the thread handling significantly, as the agent would only deal with the service side thread id, and all local context would be handled by the context provider.
    - The response would contain a id in either case, either generated by the context provider to indicate the current thread, or the service side thread id, a subsequent run with that id/thread would then continue the conversation and the context provider decides if it should add the full history or not.

    #### 2. Variant with a default Context Provider that can store messages, that can be overridden by other context providers
    This approach would mean:
    - Creating a default context provider that stores chat messages, that can be overridden by other context providers, but the agent would still deal with both local and service side threads, and the context provider would just be an additional way to add context to the conversation.
    - This means that alternative context providers become responsible for storing messages locally, which can lead to confusion and inconsistencies, as different context providers might have different ways of storing messages, and the agent would still need to deal with both local and service side threads.

### 6. Rename `Thread` for clarity.
- Another consideration is if we should continue the `Thread` name or move to something else like `Conversation` or `Context`, that would be a bigger breaking change initially but would be clearer in the long run. This ADR will keep using `Thread` for now for consistency. One of the reasons for it is to clarify that it is not focused only on chat and messages, but especially for workflows, it is a broader concept.


# TO BE UPDATED BELOW THIS LINE
# -----------------------------
## Pros and Cons of the Options
So that gives the following:
- Good, because it is explicit about the type of thread being used. (solve for issue 1)
- Good, because it is clear which chat clients support which type of thread. (solve for issue 1)
- Good, because we can make all the logic that deals with thr eads much clearer, as each class has a single responsibility. (solve for issue 1 and 2)
- Good, because the simplified state-only context data make the threads much easier to (de)serialize and (re)store. (solve for issue 2 and 3)
- Good, because it makes it easier to serialize and deserialize threads. (solve for issue 3)
- Bad, because it requires mandating serializable context data/state from context providers, which might be limiting for some use cases.
- Bad, because users will need to switch from one `get_new_thread` method to two different methods `get_remote_thread` and `get_local_thread` and there may be a situation when one of the methods will throw an exception. While `get_new_thread` always returns some instance. We could mitigate this with a deprecated `get_new_thread` method that calls one of the two new methods based on parameters, but that would add complexity and might be confusing and in the long run cause another breaking change when removed.

## Agent Thread Invocation Flow with Option 2

### Local Thread Flow

The following diagram illustrates the flow when using a local thread. The `get_messages` and `add_messages` methods should be async and can thus be used to store a thread long-term, similar to the current ChatMessageStore. The `context providers` are invoked by the agent, against it's own attribute.

Creating a thread:

```mermaid
sequenceDiagram
        participant User
    box Agent Layer
        participant Agent
        participant LocalThread
        participant ContextProvider
    end


    User->>Agent: get_local_thread()
    Agent->>LocalThread: initialize
    LocalThread-->>Agent: thread: LocalThread
    Agent<<->>ContextProvider: thread_created(thread)
    Agent-->>User: thread
```

Using the thread:
```mermaid
sequenceDiagram
        participant User
        participant LocalThread
    box Agent Layer
        participant Agent
        participant ContextProvider
    end
    box LLM Layer
        participant ChatClient
    end
        participant LLM

    User->>Agent: run(messages, thread, options)
    Agent<<->>LocalThread: get_messages()
    Agent<<->>ContextProvider: invoking(messages, thread)
    Agent->>ChatClient: get_response(messages, options)
    ChatClient<<->>LLM: call(messages, options)
    ChatClient-->>Agent: response: ChatResponse
    Agent->>LocalThread: add_messages(response.messages)
    Agent->>ContextProvider: invoked(response, thread)
    Agent-->>User: response: AgentRunResponse
```

### Remote Thread Flow

The following diagram illustrates the flow when using a remote/service thread. When the thread does not have a ID yet, it sets `store=True` and then it will be updated after the run.

Creating a thread:

```mermaid
sequenceDiagram
        participant User
    box Agent Layer
        participant Agent
        participant RemoteThread
        participant ContextProvider
    end


    User->>Agent: get_remote_thread()
    Agent->>RemoteThread: initialize
    RemoteThread-->>Agent: thread: RemoteThread
    Agent<<->>ContextProvider: thread_created(thread)
    Agent-->>User: thread
```

Using the thread:

```mermaid
sequenceDiagram
        participant User
        participant RemoteThread
    box Agent Layer
        participant Agent
        participant ContextProvider
    end
    box LLM Layer
        participant ChatClient
    end
        participant LLM

    User->>Agent: run(message, thread, options)
    Agent<<->>RemoteThread: overwrite store and conversation_id
    Agent<<->>ContextProvider: invoking(messages, thread)
    Agent->>ChatClient: get_response(messages, options)
    ChatClient<<->>LLM: call(messages, options)
    ChatClient-->>Agent: response: ChatResponse
    Agent->>RemoteThread: update_thread_id(response)
    Agent->>ContextProvider: invoked(response, thread)
    Agent-->>User: response: AgentRunResponse
```

### Hosted app thread flow (local flow shown, same setup would apply to the remote flow)

In a hosted environment, such as Azure Functions or when creating a A2A agent, the app layer would be responsible for loading and saving the thread before and after the run, as illustrated below, having the simpler thread types makes this much simpler as well, and provides complete configurability to the ThreadStore and app layer on how they want to deal with threads. The `af_thread_id` in this diagram is just a placeholder for whatever ID the app layer wants to use to identify the thread.

```mermaid
sequenceDiagram

        participant User
    box Hosting
        participant App
        participant ThreadStore
        participant LocalThread
        participant Agent
        participant ContextProvider
        participant ChatClient
    end
        participant LLM

    User->>App: call(message, af_thread_id, options)
    App->>ThreadStore: get(af_thread_id)
    ThreadStore-->>App: thread
    App->>Agent: run(message, thread, options)
    Agent<<->>LocalThread: get_messages()
    Agent<<->>ContextProvider: invoking(messages, thread)
    Agent->>ChatClient: get_response(messages, options)
    ChatClient<<->>LLM: call(messages, options)
    ChatClient-->>Agent: response: ChatResponse
    Agent->>LocalThread: add_messages(response.messages)
    Agent->>ContextProvider: invoked(response, thread)
    Agent-->>App: response: AgentRunResponse
    App->>ThreadStore: save(af_thread_id, thread)
    App-->>User: response in app format
```


## Decision Outcome

TBD
