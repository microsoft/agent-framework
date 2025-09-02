# Microsoft Agent Framework Agent Types

The Microsoft Agent Framework provides support for several types of agents to accommodate different use cases and requirements.

All agents implement a common protocol, `AIAgent`, which provides a consistent interface for all agent types. This allows for building common, agent agnostic, higher level functionality such as multi-agent orchestrations.

Let's dive into each agent type in more detail.

## Simple agents based on inference services

The agent framework makes it easy to create simple agents based on many different inference services.
Any inference service that provides a chat client implementation can be used to build these agents.

These agents support a wide range of functionality out of the box:

1. Function calling
1. Multi-turn conversations with local chat history management or service provided chat history management
1. Custom service provided tools (e.g. MCP, Code Execution)
1. Structured output
1. Streaming responses

To create one of these agents, simply construct a `ChatClientAgent` using the chat client implementation of your choice.

```python
from agent_framework import ChatClientAgent
from agent_framework.openai import OpenAIChatClient

agent = ChatClientAgent(
    chat_client=OpenAIChatClient(),
    instructions="You are a helpful assistant"
)
```

Alternatively, you can use the convenience method on the chat client:

```python
from agent_framework.openai import OpenAIChatClient

agent = OpenAIChatClient().create_agent(
    instructions="You are a helpful assistant"
)
```

### Function Tools

You can provide function tools to agents for enhanced capabilities:

```python
from typing import Annotated

def get_weather(location: Annotated[str, "The location to get the weather for."]) -> str:
    """Get the weather for a given location."""
    return f"The weather in {location} is sunny with a high of 25°C."

agent = OpenAIChatClient().create_agent(
    instructions="You are a helpful weather assistant.",
    tools=get_weather
)
```

### Streaming Responses

Agents support both regular and streaming responses:

```python
# Regular response (wait for complete result)
response = await agent.run("What's the weather like in Seattle?")
print(response.text)

# Streaming response (get results as they are generated)
async for chunk in agent.run_streaming("What's the weather like in Portland?"):
    if chunk.text:
        print(chunk.text, end="", flush=True)
```

### MCP (Model Context Protocol) Tools

The framework supports MCP tools for enhanced agent capabilities:

```python
from agent_framework import McpStreamableHttpTool

# Tools can be provided at agent creation
agent = OpenAIChatClient().create_agent(
    instructions="You are a helpful assistant.",
    tools=McpStreamableHttpTool(
        name="Microsoft Learn MCP",
        url="https://learn.microsoft.com/api/mcp"
    )
)

# Or provided at runtime
mcp_tool = McpStreamableHttpTool(
    name="Microsoft Learn MCP", 
    url="https://learn.microsoft.com/api/mcp"
)
response = await agent.run("How to create Azure storage?", tools=mcp_tool)
```

## Custom agents

It is also possible to create fully custom agents that are not just wrappers around a chat client.
Agent Framework provides the `AIAgent` protocol and `AgentBase` base class, which when implemented/subclassed allows for complete control over the agent's behavior and capabilities.

```python
from agent_framework import AgentBase, AgentRunResponse, AgentRunResponseUpdate, AgentThread, ChatMessage
from collections.abc import AsyncIterable

class CustomAgent(AgentBase):
    async def run(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AgentRunResponse:
        # Custom agent implementation
        pass
    
    def run_streaming(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentRunResponseUpdate]:
        # Custom streaming implementation
        pass
```
