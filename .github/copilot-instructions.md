# GitHub Copilot Instructions for Microsoft Agent Framework

## Project Overview
This is the Microsoft Agent Framework - a comprehensive, cross-platform (Python & .NET) framework for building, orchestrating, and deploying AI agents and multi-agent systems. The framework emphasizes simplicity, modularity, and enterprise-ready deployment capabilities.

## Core Architecture Principles

### 1. Design Philosophy
- **Simplicity First**: Avoid "kitchen-sink" agents that are hard to understand and maintain
- **Composability**: Components should be easily combined to create complex systems
- **Cross-Platform**: Native support for both Python 3.10+ and .NET
- **Enterprise Ready**: Built-in observability, telemetry, and deployment support
- **Async-First**: All I/O operations should be asynchronous by default

### 2. Component Hierarchy
```
Component (Base)
├── Agent Components
│   ├── Model Client (OpenAI, Azure OpenAI, Azure AI Foundry)
│   ├── Vector Store & Embedding Client
│   ├── Tools (Functions, OpenAPI, MCP servers)
│   ├── Context Provider (Memory, RAG)
│   ├── Thread (Conversation management)
│   └── Guardrails
└── Agents & Workflows
    ├── Agent (Individual AI agent)
    └── Workflow (Multi-agent orchestration)
```

## Python Development Guidelines

### 1. Code Quality Standards

#### Async/Await Patterns
- **ALWAYS use async/await** for I/O operations
- **NEVER block** the event loop with synchronous calls
- Use `AsyncIterable` for streaming responses

```python
# ✅ GOOD: Async by default
async def run(self, messages: str | ChatMessage) -> AgentRunResponse:
    result = await self.chat_client.get_response(messages)
    return result

# ✅ GOOD: Streaming support
async def run_streaming(self, messages: str | ChatMessage) -> AsyncIterable[AgentRunResponseUpdate]:
    async for chunk in self.chat_client.get_streaming_response(messages):
        yield AgentRunResponseUpdate(text=chunk.text, role=chunk.role)

# ❌ BAD: Blocking call
def run_sync(self, messages):
    return requests.post("https://api.openai.com/v1/chat/completions")
```

#### Type Safety
- **Use comprehensive type hints** everywhere
- **Leverage generics** and TypeVars for reusable components
- **Use Literal types** for string constants
- **Prefer protocols** over inheritance where appropriate

```python
# ✅ GOOD: Comprehensive typing
from typing import Literal, Protocol, TypeVar, Generic
from collections.abc import AsyncIterable

TThreadType = TypeVar("TThreadType", bound="AgentThread")

class Agent(Protocol, Generic[TThreadType]):
    async def run(
        self, 
        messages: str | ChatMessage | list[ChatMessage],
        *,
        thread: TThreadType | None = None,
        tool_choice: Literal["auto", "required", "none"] | ChatToolMode = "auto"
    ) -> AgentRunResponse:
        ...

# ❌ BAD: Missing types
def run(self, messages, thread=None):
    return self.client.get_response(messages)
```

### 2. Pydantic Best Practices

#### Model Configuration
- **Use AFBaseModel** as the base class for all data models
- **Enable validate_assignment** for runtime validation
- **Use Field() for documentation** and validation

```python
# ✅ GOOD: Optimized Pydantic model
from agent_framework._pydantic import AFBaseModel
from pydantic import Field
from typing import Literal

class ChatMessage(AFBaseModel):
    """A message in a chat conversation."""
    
    role: Literal["user", "assistant", "system"] = Field(
        description="The role of the message sender"
    )
    text: str = Field(description="The message content")
    metadata: dict[str, Any] = Field(default_factory=dict)

# ❌ BAD: No base class, missing validation
class ChatMessage:
    def __init__(self, role, text, metadata=None):
        self.role = role
        self.text = text
        self.metadata = metadata or {}
```

#### Settings Management
- **Use AFBaseSettings** for configuration
- **Support environment variables** with proper prefixes
- **Provide sensible defaults**

```python
# ✅ GOOD: Settings with env support
class OpenAISettings(AFBaseSettings):
    env_prefix: ClassVar[str] = "OPENAI_"
    
    api_key: SecretStr = Field(description="OpenAI API key")
    model: str = Field(default="gpt-4", description="Model to use")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
```

### 3. Performance Optimization

#### Use Modern Libraries
- **httpx** for HTTP/2 support and better async performance
- **orjson** for faster JSON serialization (2-3x faster than stdlib)
- **uvloop** for faster event loops (optional, fallback gracefully)

```python
# ✅ GOOD: Modern HTTP client
import httpx

class ModernChatClient:
    def __init__(self):
        self.client = httpx.AsyncClient(
            http2=True,
            limits=httpx.Limits(max_keepalive_connections=20)
        )

# ✅ GOOD: Fast JSON with fallback
try:
    import orjson as json
except ImportError:
    import json
```

#### Memory Efficiency
- **Use generators and async generators** for large datasets
- **Implement proper cleanup** with context managers
- **Avoid loading everything into memory**

```python
# ✅ GOOD: Memory-efficient streaming
async def process_messages(self) -> AsyncIterable[ProcessedMessage]:
    async for raw_message in self.stream_messages():
        processed = await self.process_single_message(raw_message)
        yield processed  # Don't accumulate in memory

# ✅ GOOD: Proper resource cleanup
class ChatClient:
    async def __aenter__(self):
        self.session = httpx.AsyncClient()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.session.aclose()
```

### 4. Error Handling

#### Custom Exceptions
- **Use specific exception types** from `agent_framework.exceptions`
- **Provide meaningful error messages**
- **Include context** for debugging

```python
# ✅ GOOD: Specific exceptions
from agent_framework.exceptions import AgentExecutionException, ServiceResponseException

async def run_agent(self, messages: list[ChatMessage]) -> AgentRunResponse:
    try:
        response = await self.chat_client.get_response(messages)
        return AgentRunResponse(messages=response.messages)
    except httpx.HTTPStatusError as e:
        raise ServiceResponseException(
            f"HTTP {e.response.status_code}: {e.response.text}"
        ) from e
    except Exception as e:
        raise AgentExecutionException(
            f"Failed to execute agent: {str(e)}"
        ) from e
```

### 5. Tool Development

#### Function Tools
- **Use @ai_function decorator** for automatic schema generation
- **Provide clear descriptions** for LLM understanding
- **Use Annotated with Field** for parameter documentation

```python
# ✅ GOOD: Well-documented tool
from typing import Annotated
from pydantic import Field
from agent_framework import ai_function

@ai_function(name="get_weather", description="Get current weather for a location")
def get_weather(
    location: Annotated[str, Field(description="City name or coordinates")],
    units: Annotated[Literal["celsius", "fahrenheit"], Field(description="Temperature units")] = "celsius"
) -> str:
    """Get the current weather for a given location.
    
    Args:
        location: The city name or coordinates to get weather for
        units: Temperature units to use
        
    Returns:
        A formatted weather report string
    """
    # Implementation here
    return f"Weather in {location}: 22°{units[0].upper()}, sunny"
```

### 6. Testing Patterns

#### Async Testing
- **Use pytest-asyncio** for async test support
- **Mock external dependencies** properly
- **Test both success and failure cases**

```python
# ✅ GOOD: Async test with mocking
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_chat_client_success():
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value.json.return_value = {
            "choices": [{"message": {"content": "Hello!"}}]
        }
        
        client = ChatClient(api_key="test")
        response = await client.get_response("Hi")
        
        assert response.text == "Hello!"
        mock_post.assert_called_once()

@pytest.mark.asyncio
async def test_chat_client_failure():
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.side_effect = httpx.HTTPStatusError("500", request=None, response=None)
        
        client = ChatClient(api_key="test")
        with pytest.raises(ServiceResponseException):
            await client.get_response("Hi")
```

## Multi-Agent Orchestration Patterns

### 1. Sequential Workflows
```python
# ✅ GOOD: Sequential agent workflow
async def sequential_workflow(task: str) -> str:
    # Step 1: Research agent gathers information
    research_result = await research_agent.run(f"Research: {task}")
    
    # Step 2: Analysis agent processes the research
    analysis_result = await analysis_agent.run(f"Analyze: {research_result}")
    
    # Step 3: Writer agent creates final output
    final_result = await writer_agent.run(f"Write: {analysis_result}")
    
    return final_result
```

### 2. Parallel Workflows
```python
# ✅ GOOD: Parallel agent execution
import asyncio

async def parallel_workflow(task: str) -> str:
    # Run multiple agents in parallel
    results = await asyncio.gather(
        agent1.run(f"Perspective A: {task}"),
        agent2.run(f"Perspective B: {task}"),
        agent3.run(f"Perspective C: {task}")
    )
    
    # Aggregate results
    aggregated = await aggregator_agent.run(f"Combine: {results}")
    return aggregated
```

## Telemetry and Observability

### 1. OpenTelemetry Integration
- **Use @use_telemetry decorator** for automatic tracing
- **Add custom spans** for important operations
- **Include relevant attributes** for debugging

```python
# ✅ GOOD: Proper telemetry
from agent_framework.telemetry import use_telemetry
from opentelemetry import trace

@use_telemetry
class ChatClient:
    async def get_response(self, messages: list[ChatMessage]) -> ChatResponse:
        tracer = trace.get_tracer(__name__)
        
        with tracer.start_as_current_span("chat_completion") as span:
            span.set_attribute("message_count", len(messages))
            span.set_attribute("model", self.model)
            
            response = await self._make_request(messages)
            
            span.set_attribute("tokens_used", response.usage.total_tokens)
            return response
```

## Documentation Standards

### 1. Docstring Format
- **Use Google-style docstrings**
- **Document all parameters and return values**
- **Include examples** for complex functions

```python
# ✅ GOOD: Comprehensive docstring
async def run_agent(
    self,
    messages: str | ChatMessage | list[ChatMessage],
    *,
    thread: AgentThread | None = None,
    **kwargs: Any
) -> AgentRunResponse:
    """Run the agent with the given messages.
    
    This method executes the agent's main logic, processing input messages
    and returning a structured response. The agent may use tools, access
    memory, and perform multiple model calls as needed.
    
    Args:
        messages: The input message(s) to process. Can be a single string,
            ChatMessage object, or list of ChatMessage objects.
        thread: Optional conversation thread for maintaining context.
            If None, a new thread will be created.
        **kwargs: Additional keyword arguments passed to the underlying
            chat client (e.g., temperature, max_tokens).
    
    Returns:
        An AgentRunResponse containing the agent's response messages,
        usage statistics, and any additional metadata.
        
    Raises:
        AgentExecutionException: If the agent fails to process the messages.
        ServiceResponseException: If the underlying service returns an error.
        
    Example:
        ```python
        agent = ChatClientAgent(chat_client=OpenAIChatClient())
        response = await agent.run("What's the weather like?")
        print(response.text)
        ```
    """
```

## File Organization

### 1. Module Structure
- **Use _private.py** for internal implementations
- **Expose public APIs** through __init__.py
- **Group related functionality** in single files when reasonable

```python
# ✅ GOOD: Clean module organization
# agent_framework/__init__.py
from ._agents import ChatClientAgent, AgentBase
from ._clients import ChatClient, ChatClientBase
from ._types import ChatMessage, ChatResponse
from ._tools import ai_function, AITool

__all__ = [
    "ChatClientAgent",
    "AgentBase", 
    "ChatClient",
    "ChatClientBase",
    "ChatMessage",
    "ChatResponse",
    "ai_function",
    "AITool"
]
```

## Common Anti-Patterns to Avoid

### ❌ Don't Do This:
```python
# Blocking I/O in async context
def bad_async_function():
    response = requests.get("https://api.example.com")  # Blocks event loop
    return response.json()

# Missing type hints
def process_data(data, options=None):
    if options is None:
        options = {}
    return data.transform(options)

# Not using Pydantic for data validation
class BadDataClass:
    def __init__(self, value):
        self.value = value  # No validation

# Mixing sync and async patterns
class InconsistentClient:
    def sync_method(self):
        return "result"
    
    async def async_method(self):
        return await self.get_data()
```

## Summary

When contributing to this project, prioritize:
1. **Async-first design** with comprehensive type hints
2. **Pydantic v2** for all data models and settings
3. **Performance optimization** with modern libraries
4. **Proper error handling** with specific exceptions
5. **Comprehensive testing** with async support
6. **Clear documentation** with examples
7. **Observability** through OpenTelemetry integration

Follow these guidelines to maintain consistency with the existing codebase and ensure high-quality, performant code that aligns with the framework's enterprise-ready goals.
