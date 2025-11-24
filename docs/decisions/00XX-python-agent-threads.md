---
status: Proposed
contact: eavanvalkenburg
date: 2025-11-24
deciders: markwallace-microsoft, dmytrostruk, taochenosu, alliscode, moonbox3
consulted: sergeymenshykh, rbarreto, dmytrostruk, westey-m
---

# Agent Threads in Python

## Context and Problem Statement

Currently in Python we use `threads` in the following way: we have a single thread class, called `AgentThread`, which is responsible for holding either a `ChatMessageStore` or a `service_thread_id`, but not both.
- Generally you create a thread by calling `agent.get_new_thread()` which can take some arguments as well.
- It can then be used, if you use it by passing it to a `agent.run` or `agent.run_stream` call, with `store=True`, it will then attempt (if the chat client supports that) to create a thread in the service, we will then store the response_id as the `service_thread_id` in the `AgentThread` instance.
- If you use it with `store=False`, it will try to call the `ChatMessageStoreFactory` on the agent to get a new `ChatMessageStore` instance, which will then be stored in the `AgentThread` instance.
- However before all of that a thread is `uninitialized`, meaning it has neither a `ChatMessageStore` nor a `service_thread_id`.
- It also has a method called `on_new_messages` which does nothing when called to a thread that has a `service_thread_id`, but when called to a thread that has a `ChatMessageStore`, it will call the `add_messages` method of the `ChatMessageStore` instance.
This all means that at various moments a thread can be different things and have different behaviors, which can be confusing for users. It is also unclear which chat clients can support which type of thread, and what the implications are of using one or the other, in combination with the `store` parameter.

## Decision Drivers

- Ease of use: make it easy for users to understand how to use threads in the Python SDK -> Zen of Python: "Explicit is better than implicit".
- Clarity: make it clear what a thread is and what it can do.

## Considered Options

1. Current approach with a single `AgentThread` class that can hold either a `ChatMessageStore` or a `service_thread_id`.
1. Separate classes for remote thread and local thread, each with their own behaviors and methods.

### 1. Current approach with a single `AgentThread` class that can hold either a `ChatMessageStore` or a `service_thread_id`.
- Good, because it is a single class that can be used for both types of threads.
- Good, because it is easy to create a new thread by calling `agent.get_new_thread()`.
- Good, because it is consistent with dotnet.
- Bad, because it can be confusing for users to understand the different states of a thread.
- Bad, because it is unclear which chat clients can support which type of thread.
- Bad, because dotnet also has subclasses for each type of agent, so already somewhat diverging from dotnet.

### 2. Separate classes for `ServiceThread`/`RemoteThread` and `LocalAgentThread`/`LocalThread`, each with their own behaviors and methods.
This approach would mean:
- Creating two subclasses of AgentThread, one for service threads and one for local threads, both with `context providers` as attributes, but with different other attributes and methods.
- We would then add a flag on ChatClients, to indicate which type of thread they support, and it can be both, so two flags are likely needed, although local thread might always be possible.
- And finally, all Agents would get two methods, `get_service_thread()`/`get_remote_thread` and `get_local_thread()`, both of which might raise an error if the chat client does not support that type of thread.
- the `run` methods would take both types of threads, but would raise an error if the thread type is not supported by the chat client. And it would also check with the `store` parameter to make sure it is used correctly, or set it correctly.
- One open question is how to handle when there is a mismatch between the thread type and the `store` parameter, for example passing a `LocalAgentThread` with `store=True`, or a `ServiceAgentThread` with `store=False`. Options are to either raise an error, or to ignore the `store` parameter and always do the right thing based on the thread type. Or to transform the thread into the right type, but that seems more complex and might not always be possible. Although starting with a local thread (which would be a list of chat messages in a ChatMessageStore) and then setting store=True might make sense, the return would be a service thread then, but that adds complexity, this might be useful for workflows that combine different agent types.
- Naming is another open question, options are:
    - for the remote threads:
        - `ServiceThread`
        - `RemoteThread`
        - `ServiceSideThread`
    - for the local threads:
        - `LocalAgentThread`
        - `LocalThread`
        - `ClientSideThread`

    `RemoteThread` and `LocalThread` seem the clearest and most concise options and the most pythonic.

So that gives the following:
- Good, because it is explicit about the type of thread being used.
- Good, because it is clear which chat clients support which type of thread.
- Good, because we can make all the logic that deals with threads much clearer, as each class has a single responsibility.
- Good, because it might also enable a abstracted method to get a list of chat messages from a thread through the chat client.
- Bad, because it would more fundamentally diverge from dotnet.

## Decision Outcome

TBD
