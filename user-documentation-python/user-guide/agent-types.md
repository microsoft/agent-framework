# Microsoft Agent Framework Agent Types

The Microsoft Agent Framework provides support for several types of agents to accommodate different use cases and requirements.

All agents implement a common protocol, `AgentProtocol`, which provides a consistent interface for all agent types. This allows for building common, agent agnostic, higher level functionality such as multi-agent orchestrations.

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

To create one of these agents, simply construct a `ChatAgent` using the chat client implementation of your choice.

```python
from agent_framework import ChatAgent
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential

async with (
    AzureCliCredential() as credential,
    ChatAgent(
        chat_client=FoundryChatClient(async_credential=credential),
        instructions="You are a helpful assistant"
    ) as agent
):
    response = await agent.run("Hello!")
```

Alternatively, you can use the convenience method on the chat client:

```python
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential

async with AzureCliCredential() as credential:
    agent = FoundryChatClient(async_credential=credential).create_agent(
        instructions="You are a helpful assistant"
    )
```

For detailed examples, see:
- [Basic Foundry agent](../../../python/samples/getting_started/agents/foundry/foundry_basic.py)
- [Foundry with explicit settings](../../../python/samples/getting_started/agents/foundry/foundry_with_explicit_settings.py)
- [Using existing Foundry agent](../../../python/samples/getting_started/agents/foundry/foundry_with_existing_agent.py)

### Function Tools

You can provide function tools to agents for enhanced capabilities:

```python
from typing import Annotated
from pydantic import Field
from azure.identity.aio import AzureCliCredential

def get_weather(location: Annotated[str, Field(description="The location to get the weather for.")]) -> str:
    """Get the weather for a given location."""
    return f"The weather in {location} is sunny with a high of 25°C."

async with (
    AzureCliCredential() as credential,
    FoundryChatClient(async_credential=credential).create_agent(
        instructions="You are a helpful weather assistant.",
        tools=get_weather
    ) as agent
):
    response = await agent.run("What's the weather in Seattle?")
```

For complete examples with function tools, see:
- [Foundry with function tools](../../../python/samples/getting_started/agents/foundry/foundry_with_function_tools.py)

### Streaming Responses

Agents support both regular and streaming responses:

```python
# Regular response (wait for complete result)
response = await agent.run("What's the weather like in Seattle?")
print(response.text)

# Streaming response (get results as they are generated)
async for chunk in agent.run_stream("What's the weather like in Portland?"):
    if chunk.text:
        print(chunk.text, end="", flush=True)
```

For streaming examples, see:
- [Foundry streaming examples](../../../python/samples/getting_started/agents/foundry/foundry_basic.py)

### Code Interpreter Tools

Foundry agents support hosted code interpreter tools for executing Python code:

```python
from agent_framework import ChatAgent, HostedCodeInterpreterTool
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential

async with (
    AzureCliCredential() as credential,
    ChatAgent(
        chat_client=FoundryChatClient(async_credential=credential),
        instructions="You are a helpful assistant that can execute Python code.",
        tools=HostedCodeInterpreterTool()
    ) as agent
):
    response = await agent.run("Calculate the factorial of 100 using Python")
```

For code interpreter examples, see:
- [Foundry with code interpreter](../../../python/samples/getting_started/agents/foundry/foundry_with_code_interpreter.py)

### Model Context Protocol (MCP) Tools

Foundry agents support Model Context Protocol (MCP) tools for connecting to external services and data sources.

Learn more about MCP tools in the [Azure AI Foundry documentation](https://learn.microsoft.com/en-us/azure/ai-foundry/agents/how-to/tools/model-context-protocol).

```python
from agent_framework import ChatAgent, MCPStreamableHTTPTool
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import AzureCliCredential

# Tools can be defined at agent creation
async with (
    AzureCliCredential() as credential,
    FoundryChatClient(async_credential=credential).create_agent(
        name="DocsAgent",
        instructions="You are a helpful assistant that can help with microsoft documentation questions.",
        tools=MCPStreamableHTTPTool(
            name="Microsoft Learn MCP",
            url="https://learn.microsoft.com/api/mcp",
        ),
    ) as agent
):
    response = await agent.run("How to create an Azure storage account using az cli?")
```

You can also provide MCP tools when running the agent:

```python
async with (
    AzureCliCredential() as credential,
    MCPStreamableHTTPTool(
        name="Microsoft Learn MCP",
        url="https://learn.microsoft.com/api/mcp",
    ) as mcp_server,
    ChatAgent(
        chat_client=FoundryChatClient(async_credential=credential),
        name="DocsAgent",
        instructions="You are a helpful assistant that can help with microsoft documentation questions.",
    ) as agent,
):
    response = await agent.run("What is Microsoft Semantic Kernel?", tools=mcp_server)
```

For complete MCP examples, see:
- [Foundry with MCP tools](../../../python/samples/getting_started/agents/foundry/foundry_with_local_mcp.py)

## Custom agents

It is also possible to create fully custom agents that are not just wrappers around a chat client.
Agent Framework provides the `AgentProtocol` protocol and `BaseAgent` base class, which when implemented/subclassed allows for complete control over the agent's behavior and capabilities.

```python
from agent_framework import BaseAgent, AgentRunResponse, AgentRunResponseUpdate, AgentThread, ChatMessage
from collections.abc import AsyncIterable

class CustomAgent(BaseAgent):
    async def run(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AgentRunResponse:
        # Custom agent implementation
        pass

    def run_stream(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentRunResponseUpdate]:
        # Custom streaming implementation
        pass
```
