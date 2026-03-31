# Core Package (agent-framework-core)

The foundation package containing all core abstractions, types, and built-in OpenAI/Azure OpenAI support.

## Module Structure

```
agent_framework/
├── __init__.py          # Public API exports
├── _agents.py           # Agent implementations
├── _clients.py          # Chat client base classes and protocols
├── _types.py            # Core types (Message, ChatResponse, Content, etc.)
├── _tools.py            # Tool definitions and function invocation
├── _middleware.py       # Middleware system for request/response interception
├── _sessions.py         # AgentSession and context provider abstractions
├── _skills.py           # Agent Skills system (models, executors, provider)
├── _mcp.py              # Model Context Protocol support
├── _workflows/          # Workflow orchestration (sequential, concurrent, handoff, etc.)
├── openai/              # Built-in OpenAI client
├── azure/               # Lazy-loading entry point for Azure integrations
└── <provider>/          # Other lazy-loading provider folders
```

## Core Classes

### Agents (`_agents.py`)

- **`SupportsAgentRun`** - Protocol defining the agent interface
- **`BaseAgent`** - Abstract base class for agents
- **`Agent`** - Main agent class wrapping a chat client with tools, instructions, and middleware

### Chat Clients (`_clients.py`)

- **`SupportsChatGetResponse`** - Protocol for chat client implementations
- **`BaseChatClient`** - Abstract base class with middleware support; subclasses implement `_inner_get_response()` and `_inner_get_streaming_response()`

### Types (`_types.py`)

- **`Message`** - Represents a chat message with role, content, and metadata
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
- **`AgentContext`** / **`ChatContext`** / **`FunctionInvocationContext`** - Context objects passed through middleware

### Sessions (`_sessions.py`)

- **`AgentSession`** - Manages conversation state and session metadata
- **`SessionContext`** - Context object for session-scoped data during agent runs
- **`BaseContextProvider`** - Base class for context providers (RAG, memory systems)
- **`BaseHistoryProvider`** - Base class for conversation history storage

### Skills (`_skills.py`)

- **`Skill`** - A skill definition bundling instructions (`content`) with metadata, resources, and scripts. Supports `@skill.resource` and `@skill.script` decorators for adding components.
- **`SkillResource`** - Named supplementary content attached to a skill; holds either static `content` or a dynamic `function` (sync or async). Exactly one must be provided.
- **`SkillScript`** - An executable script attached to a skill; holds either an inline `function` (code-defined, runs in-process) or a `path` to a file on disk (file-based, delegated to a runner). Exactly one must be provided.
- **`SkillScriptRunner`** - Protocol for file-based script execution. Any callable matching `(skill, script, args) -> Any` satisfies it. Code-defined scripts do not use a runner.
- **`SkillsProvider`** - Context provider (extends `BaseContextProvider`) that discovers file-based skills from `SKILL.md` files and/or accepts code-defined `Skill` instances. Follows progressive disclosure: advertise → load → read resources / run scripts.

### Workflows (`_workflows/`)

- **`Workflow`** - Graph-based workflow definition
- **`WorkflowBuilder`** - Fluent API for building workflows
- **Orchestrators**: `SequentialOrchestrator`, `ConcurrentOrchestrator`, `GroupChatOrchestrator`, `MagenticOrchestrator`, `HandoffOrchestrator`

## Built-in Providers

### OpenAI (`openai/`)

- **`OpenAIChatClient`** - Chat client for the OpenAI Responses API
- **`OpenAIChatCompletionClient`** - Chat client for the OpenAI Chat Completions API

### Foundry (`foundry/`)

- **`FoundryChatClient`** - Chat client for Azure AI Foundry project endpoints

## Key Patterns

### Creating an Agent

```python
from agent_framework import Agent
from agent_framework.openai import OpenAIChatClient

agent = Agent(
    client=OpenAIChatClient(),
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
from agent_framework import Agent, AgentMiddleware, AgentContext

class LoggingMiddleware(AgentMiddleware):
    async def process(self, context: AgentContext, call_next) -> None:
        print(f"Input: {context.messages}")
        await call_next()
        print(f"Output: {context.result}")

agent = Agent(..., middleware=[LoggingMiddleware()])
```

### Custom Chat Client

```python
from agent_framework import BaseChatClient, ChatResponse, Message

class MyClient(BaseChatClient):
    async def _inner_get_response(self, *, messages, options, **kwargs) -> ChatResponse:
        # Call your LLM here
        return ChatResponse(messages=[Message(role="assistant", text="Hi!")])

    async def _inner_get_streaming_response(self, *, messages, options, **kwargs):
        yield ChatResponseUpdate(...)
```
