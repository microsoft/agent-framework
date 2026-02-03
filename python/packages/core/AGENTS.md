# Core Package (agent-framework-core)

The foundation package containing all core abstractions, types, and built-in OpenAI/Azure OpenAI support.

## Module Structure

```
agent_framework/
├── __init__.py          # Public API exports
├── _agents.py           # Agent implementations
├── _clients.py          # Chat client base classes and protocols
├── _types.py            # Core types (ChatMessage, ChatResponse, Content, etc.)
├── _tools.py            # Tool definitions and function invocation
├── _middleware.py       # Middleware system for request/response interception
├── _threads.py          # AgentThread and message store abstractions
├── _memory.py           # Context providers for memory/RAG
├── _mcp.py              # Model Context Protocol support
├── _workflows/          # Workflow orchestration (sequential, concurrent, handoff, etc.)
├── openai/              # Built-in OpenAI client
├── azure/               # Lazy-loading entry point for Azure integrations
└── <provider>/          # Other lazy-loading provider folders
```

## Core Classes

### Agents (`_agents.py`)

- **`AgentProtocol`** - Protocol defining the agent interface
- **`BaseAgent`** - Abstract base class for agents
- **`ChatAgent`** - Main agent class wrapping a chat client with tools, instructions, and middleware

### Chat Clients (`_clients.py`)

- **`ChatClientProtocol`** - Protocol for chat client implementations
- **`BaseChatClient`** - Abstract base class with middleware support; subclasses implement `_inner_get_response()` and `_inner_get_streaming_response()`

### Types (`_types.py`)

- **`ChatMessage`** - Represents a chat message with role, content, and metadata
- **`ChatResponse`** - Response from a chat client containing messages and usage
- **`ChatResponseUpdate`** - Streaming response update
- **`AgentResponse`** / **`AgentResponseUpdate`** - Agent-level response wrappers
- **`Content`** - Base class for message content (text, function calls, images, etc.)
- **`ChatOptions`** - TypedDict for chat request options

### Tools (`_tools.py`)

- **`ToolProtocol`** - Protocol for tool definitions
- **`FunctionTool`** - Wraps Python functions as tools with JSON schema generation
- **`@tool`** decorator - Converts functions to tools
- **`use_function_invocation()`** - Decorator to add automatic function calling to chat clients

### Middleware (`_middleware.py`)

- **`AgentMiddleware`** - Intercepts agent `run()` calls
- **`ChatMiddleware`** - Intercepts chat client `get_response()` calls
- **`FunctionMiddleware`** - Intercepts function/tool invocations
- **`AgentRunContext`** / **`ChatContext`** / **`FunctionInvocationContext`** - Context objects passed through middleware

### Threads (`_threads.py`)

- **`AgentThread`** - Manages conversation history for an agent
- **`ChatMessageStoreProtocol`** - Protocol for persistent message storage
- **`ChatMessageStore`** - Default in-memory implementation

### Memory (`_memory.py`)

- **`ContextProvider`** - Protocol for providing additional context to agents (RAG, memory systems)
- **`Context`** - Container for context data

### Workflows (`_workflows/`)

- **`Workflow`** - Graph-based workflow definition
- **`WorkflowBuilder`** - Fluent API for building workflows
- **Orchestrators**: `SequentialOrchestrator`, `ConcurrentOrchestrator`, `GroupChatOrchestrator`, `MagenticOrchestrator`, `HandoffOrchestrator`

## Built-in Providers

### OpenAI (`openai/`)

- **`OpenAIChatClient`** - Chat client for OpenAI API
- **`OpenAIResponsesClient`** - Client for OpenAI Responses API

### Azure OpenAI (`azure/`)

- **`AzureOpenAIChatClient`** - Chat client for Azure OpenAI
- **`AzureOpenAIResponsesClient`** - Client for Azure OpenAI Responses API

## Key Patterns

### Creating an Agent

```python
from agent_framework import ChatAgent
from agent_framework.openai import OpenAIChatClient

agent = ChatAgent(
    chat_client=OpenAIChatClient(),
    instructions="You are helpful.",
    tools=[my_function],
)
response = await agent.run("Hello")
```

### Using `as_agent()` Shorthand

```python
agent = OpenAIChatClient().as_agent(
    name="Assistant",
    instructions="You are helpful.",
)
```

### Middleware Pipeline

```python
from agent_framework import ChatAgent, AgentMiddleware, AgentRunContext

class LoggingMiddleware(AgentMiddleware):
    async def invoke(self, context: AgentRunContext, next) -> AgentResponse:
        print(f"Input: {context.messages}")
        response = await next(context)
        print(f"Output: {response}")
        return response

agent = ChatAgent(..., middleware=[LoggingMiddleware()])
```

### Custom Chat Client

```python
from agent_framework import BaseChatClient, ChatResponse, ChatMessage

class MyClient(BaseChatClient):
    async def _inner_get_response(self, *, messages, options, **kwargs) -> ChatResponse:
        # Call your LLM here
        return ChatResponse(messages=[ChatMessage(role="assistant", text="Hi!")])

    async def _inner_get_streaming_response(self, *, messages, options, **kwargs):
        yield ChatResponseUpdate(...)
```
