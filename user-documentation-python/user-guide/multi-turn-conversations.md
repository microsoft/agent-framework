# Microsoft Agent Framework Multi-Turn Conversations and Threading

The Microsoft Agent Framework provides built-in support for managing multi-turn conversations with AI agents. This includes maintaining context across multiple interactions. Different agent types and underlying services that are used to build agents may support different threading types, and the Agent Framework abstracts these differences away, providing a consistent interface for developers.

For example, when using a `ChatAgent` based on a Foundry agent, the conversation history is persisted in the service. While when using a `ChatAgent` based on chat completion with gpt-4, the conversation history is in-memory and managed by the agent.

The differences between the underlying threading models are abstracted away via the `AgentThread` type.

## AgentThread lifecycle

### AgentThread Creation

`AgentThread` instances can be created in two ways:

1. By calling `get_new_thread()` on the agent.
1. By running the agent and not providing an `AgentThread`. In this case the agent will create a throwaway `AgentThread` with an underlying thread which will only be used for the duration of the run.

Some underlying threads may be persistently created in an underlying service, where the service requires this, e.g. Foundry Agents or OpenAI Responses. Any cleanup or deletion of these threads is the responsibility of the user.

```python
# Create a new thread.
thread = agent.get_new_thread()
# Run the agent with the thread.
response = await agent.run("Hello, how are you?", thread=thread)

# Run an agent with a temporary thread.
response = await agent.run("Hello, how are you?")
```

### AgentThread Storage

`AgentThread` instances can be serialized and stored for later use. This allows for the preservation of conversation context across different sessions or service calls.

For cases where the conversation history is stored in a service, the serialized `AgentThread` will contain an
id of the thread in the service.
For cases where the conversation history is managed in-memory, the serialized `AgentThread` will contain the messages
themselves.

```python
# Create a new thread.
thread = agent.get_new_thread()
# Run the agent with the thread.
response = await agent.run("Hello, how are you?", thread=thread)

# Serialize the thread for storage.
serialized_thread = await thread.serialize()
# Deserialize the thread state after loading from storage.
resumed_thread = await agent.deserialize_thread(serialized_thread)

# Run the agent with the resumed thread.
response = await agent.run("Hello, how are you?", thread=resumed_thread)
```

### Custom Message Stores

For in-memory threads, you can provide a custom message store implementation to control how messages are stored and retrieved:

```python
from agent_framework import AgentThread, ChatMessageList, ChatAgent
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential

# Using the default in-memory message store
thread = AgentThread(message_store=ChatMessageList())

# Or let the agent create one automatically
thread = agent.get_new_thread()

# You can also provide a custom message store factory when creating the agent
def custom_message_store_factory():
    return ChatMessageList()  # or your custom implementation

async with AzureCliCredential() as credential:
    agent = ChatAgent(
        chat_client=FoundryChatClient(async_credential=credential),
        instructions="You are a helpful assistant",
        chat_message_store_factory=custom_message_store_factory
    )
```

## Agent/AgentThread relationship

`AIAgent` instances are stateless and the same agent instance can be used with multiple `AgentThread` instances.

Not all agents support all thread types though. For example if you are using a `ChatAgent` with the responses service, `AgentThread` instances created by this agent, will not work with a `ChatAgent` using the Foundry Agent service.
This is because these services both support saving the conversation history in the service, and the `AgentThread`
only has a reference to this service managed thread.

It is therefore considered unsafe to use an `AgentThread` instance that was created by one agent with a different agent instance, unless you are aware of the underlying threading model and its implications.

## Practical Multi-Turn Example

Here's a complete example showing how to maintain context across multiple interactions:

```python
from agent_framework import ChatAgent, AgentThread
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential

async def foundry_multi_turn_example():
    async with (
        AzureCliCredential() as credential,
        ChatAgent(
            chat_client=FoundryChatClient(async_credential=credential),
            instructions="You are a helpful assistant"
        ) as agent
    ):
        # Create a thread for persistent conversation
        thread = agent.get_new_thread()

        # First interaction
        response1 = await agent.run("My name is Alice", thread=thread)
        print(f"Agent: {response1.text}")

        # Second interaction - agent remembers the name
        response2 = await agent.run("What's my name?", thread=thread)
        print(f"Agent: {response2.text}")  # Should mention "Alice"

        # Serialize thread for storage
        serialized = await thread.serialize()

        # Later, deserialize and continue conversation
        new_thread = await agent.deserialize_thread(serialized)
        response3 = await agent.run("What did we talk about?", thread=new_thread)
        print(f"Agent: {response3.text}")  # Should remember previous context
```

For complete threading examples, see:
- [Foundry with threads](../../../python/samples/getting_started/agents/foundry/foundry_with_thread.py)
- [Custom message store](../../../python/samples/getting_started/threads/custom_chat_message_store_thread.py)
- [Suspend and resume threads](../../../python/samples/getting_started/threads/suspend_resume_thread.py)

## Threading support by service / protocol

| Service | Threading Support |
|---------|--------------------|
| Foundry Agents | Service managed persistent threads |
| OpenAI Responses | Service managed persistent threads OR in-memory threads |
| OpenAI ChatCompletion | In-memory threads |
| OpenAI Assistants | Service managed threads |
