# Simple Agent

This module provides a basic implementation of the Agent framework, demonstrating how to create a custom agent that responds to messages with a pre-configured response.

## Components

- `SimpleAgent`: A concrete implementation of `Agent` that responds to messages with a fixed response. It demonstrates the core patterns of the Agent framework, including thread management and message handling.

## Usage

```python
from azure.ai.agent.simple_agent import SimpleAgent
from azure.ai.agent.common import ChatMessage, ChatRole

# Create a simple agent that responds with a fixed message
agent = SimpleAgent(
    response_text="I'm a simple agent that responds with this message.",
    name="SimpleAgent",
    description="A simple demonstration agent",
    instructions="Respond with a fixed message to any user message"
)

# Create a thread
thread = agent.get_new_thread()

# Create a message
message = ChatMessage(ChatRole.USER, "Hello, agent!")

# Run the agent
response = await agent.run_async_with_messages([message], thread)

# Print the response
print(f"Agent: {response.messages[0].content}")

# Run the agent with streaming
print("Agent: ", end="", flush=True)
async for update in agent.run_streaming_async_with_messages([message], thread):
    latest_content = update.message.content
    if len(latest_content) > 0:
        print(latest_content[-1], end="", flush=True)
print()  # Add a newline
```

## Sample

See `samples/simple_agent_sample.py` for a complete example of using the SimpleAgent in an interactive console application.
