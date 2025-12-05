---
status: Proposed
contact: eavanvalkenburg
date: 2025-11-24
deciders: markwallace-microsoft, dmytrostruk, taochenosu, alliscode, moonbox3
consulted: sergeymenshykh, rbarreto, dmytrostruk, westey-m
---

# Agent Threads Update

## Context and Problem Statement

Currently there are three main issues with the current thread setup. We have the following:
- `AgentThread` - contains: `service_thread_id`, `chat_message_store`, `context_providers`
- In dotnet there are also subclasses used such as `ChatClientAgentThread`, to handle additional logic.
- Ideally, developers create threads by calling `agent.get_new_thread()`, which can take some arguments as well.
- In python, we do not have the notion of protected methods, so we cannot prevent users from directly creating `AgentThread` instances, which can lead to confusion.

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

## Decision Drivers

- Ease of use: make it easy for users to understand how to use threads, one class, one purpose.
- Clarity: create a single way of storing and restoring threads that is clear and unambiguous.
- Ease of handling: make it easy to work with Threads and store them in a way that is easily serializable.


## Possible enhancements

1. Separate classes for remote thread and local thread, each with their own behaviors and methods.
1. Remove ChatMessageStore, use `list[ChatMessage]`, and add a ThreadStore abstraction to handle persistence.
1. Remove `ContextProvider`, replace with `context_data/state` on the thread, which the agent uses to get context from the providers when running in that thread.
1. Local threads only, adding a abstraction on ChatClient to load a thread by id, so that the local thread can always be synced with the service side thread, and the agent can then run with just the new messages compared to the last known state.
1. Service threads only, using a Context Provider to handle local messages and context, and the agent only deals with the service side thread id.
1. Rename `Thread` to `Conversation` for clarity.

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

### 2. Removing `ChatMessageStore`, use `list[ChatMessage]`, and add a `ThreadStore` abstraction to handle persistence.
This approach would mean:
- Removing `ChatMessageStore`, instead a `LocalThread` would have a list of ChatMessages as attribute.

### 3. Removing `ContextProvider`, replacing with a field `context_data`/`context_state` or a dict of `context_provider_name/id: context_data/state` on both thread types, which the agent would then use to get the context from the context providers when running in that thread.
This approach would mean:
- Moving `ContextProvider` back into Agent, replacing with a field `context_data`/`context_state` or a dict of `context_provider_name/id: context_data/state` on both thread types, which the agent would then use to get the context from the context providers when running in that thread. This makes the thread itself state-only, and the context provider can be stateless and live in the agent.
- The protocol/interface for ContextProviders would need a slight update, one to return a initial `context_data/state` object, the logic of which is maintained by the provider (whether it matches a app, user or session and what to record in there), and adding that `context_data/state` to the invoked and invoking methods. The `context_data/state` needs to be (de)serializable in a standard way, to make handling the thread easier.

### 4. Local threads only
This approach would mean:
- Adding an abstraction on ChatClient to load a thread by id from the service and cast the messages to our types, so that the local thread can always be synced with the service side thread, and the agent can then run with just the new messages compared to the last known state. This will make supporting cross-agent threads easier.

### 5. Service threads only
This approach would mean:
- Creating a default context provider that stores chat messages, when a response has a `response_id/conversation_id`, it updates that id on the thread, and sets a flag on the storage context provider to indicate that messages should not be added as context per run. If the response does not indicate it can store and continue, then the context provider adds the full history (or a reduced version) as context for the next run. This would simplify the thread handling significantly, as the agent would only deal with the service side thread id, and all local context would be handled by the context provider.
- The response would contain a id in either case, either generated by the context provider to indicate the current thread, or the service side thread id, a subsequent run with that id/thread would then continue the conversation and the context provider decides if it should add the full history or not.

### 6. Rename `Thread` to `Conversation` for clarity.
- Another consideration is if we should continue the `Thread` name or move to something else like `Conversation`, that would be a bigger breaking change initially but would be clearer in the long run. This ADR will keep using `Thread` for now for consistency.


# TO BE UPDATED BELOW THIS LINE
# -----------------------------
## Pros and Cons of the Options
So that gives the following:
- Good, because it is explicit about the type of thread being used. (solve for issue 1)
- Good, because it is clear which chat clients support which type of thread. (solve for issue 1)
- Good, because we can make all the logic that deals with threads much clearer, as each class has a single responsibility. (solve for issue 1 and 2)
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
