# Abstract Agent Module

This module provides the core abstractions for the Agent Framework. It defines the essential interfaces and base classes that all agents and agent threads implement.

## Components

### Agent

`Agent` is the abstract base class for all agents in the framework. It defines the core functionality that every agent must implement:

- Running an agent with messages
- Managing agent threads
- Handling streaming responses
- Processing agent options

The `Agent` abstract class provides default implementations for many operations but requires concrete implementations to define how to process messages.

### AgentThread

`AgentThread` is the base class for all agent threads. A thread represents a specific conversation with an agent and can store message history, conversation state, and other context.

### MessagesRetrievableThread

`MessagesRetrievableThread` is an abstract class that extends the base thread functionality to support retrieving messages from the thread. This is used by agents that need access to message history.

### MemoryAgentThread

`MemoryAgentThread` is a concrete implementation of `AgentThread` and `MessagesRetrievableThread` that stores all messages in memory. This is useful for simple agents and for testing.

### AgentRunOptions

`AgentRunOptions` encapsulates the options used when running an agent. This includes callback functions for handling intermediate messages and other runtime configuration.

## Usage

### Creating a Custom Agent

To create a custom agent, extend the `Agent` abstract class:

```python
class MyCustomAgent(Agent):
    def __init__(self, config):
        self._config = config
    
    def get_new_thread(self) -> AgentThread:
        return MemoryAgentThread()
    
    async def run_async_with_messages(self,
                                messages: Collection[ChatMessage],
                                thread: Optional[AgentThread] = None, 
                                options: Optional[AgentRunOptions] = None,
                                cancellation_token = None) -> ChatResponse:
        # Implementation for processing messages and generating a response
        # ...
        
    async def run_streaming_async_with_messages(self,
                                         messages: Collection[ChatMessage],
                                         thread: Optional[AgentThread] = None, 
                                         options: Optional[AgentRunOptions] = None,
                                         cancellation_token = None) -> AsyncIterator[ChatResponseUpdate]:
        # Implementation for processing messages and generating streaming updates
        # ...
```

### Using Threads

Threads are created and managed by agents:

```python
# Create an agent
agent = MyCustomAgent(config)

# Create a new thread
thread = agent.get_new_thread()

# Use the thread to maintain conversation state across multiple turns
response1 = await agent.run_async_with_messages([message1], thread)
response2 = await agent.run_async_with_messages([message2], thread)
```

### Using MemoryAgentThread

The `MemoryAgentThread` can be used directly:

```python
# Create a thread
thread = MemoryAgentThread()

# Add messages to the thread
thread.add_message(ChatMessage(ChatRole.SYSTEM, "You are a helpful assistant."))
thread.add_message(ChatMessage(ChatRole.USER, "Hello!"))

# Get messages from the thread
async for message in thread.get_messages_async():
    print(f"{message.role}: {message.content}")
```
