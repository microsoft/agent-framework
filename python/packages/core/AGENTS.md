# Core Package (agent-framework-core)

The foundation package containing all core abstractions, types, and built-in OpenAI/Azure OpenAI support.

## Module Structure

```
agent_framework/
├── __init__.py          # Public API exports
├── security.py          # Public security primitives, middleware, and tools
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
- **`ContextProvider`** - Base class for context providers (RAG, memory systems)
- **`HistoryProvider`** - Base class for conversation history storage
- **`InMemoryHistoryProvider`** - Built-in session-state history provider for local runs
- **`FileHistoryProvider`** - JSON Lines file-backed history provider storing one file per session with one message record per line

### Skills (`_skills.py`)

- **`Skill`** - Abstract base for a skill definition bundling instructions (`content`) with frontmatter metadata, resources, and scripts. Concrete subclasses (`InlineSkill`, `FileSkill`, `ClassSkill`) accept a `frontmatter=SkillFrontmatter(...)` argument carrying the spec fields. Adding new spec fields is done in one place — on `SkillFrontmatter` — keeping the subclass constructors stable.
- **`SkillFrontmatter`** - L1 discovery metadata for a skill (`name`, `description`, `license`, `compatibility`, `allowed_tools`, `metadata`). All fields are mutable plain attributes; the constructor validates `name`, `description`, and `compatibility` against the spec but post-construction assignments are not re-validated. Spec fields are reachable on every skill via `skill.frontmatter`.
- **`SkillResource`** - Named supplementary content attached to a skill; holds either static `content` or a dynamic `function` (sync or async). Exactly one must be provided.
- **`SkillScript`** - An executable script attached to a skill; holds either an inline `function` (code-defined, runs in-process) or a `path` to a file on disk (file-based, delegated to a runner). Exactly one must be provided.
- **`SkillScriptRunner`** - Protocol for file-based script execution. Any callable matching `(skill, script, args) -> Any` satisfies it. Code-defined scripts do not use a runner.
- **`SkillsProvider`** - Context provider (extends `ContextProvider`) that discovers file-based skills from `SKILL.md` files and/or accepts code-defined `Skill` instances. Follows progressive disclosure: advertise → load → read resources / run scripts.

### File Access Harness (`_harness/_file_access.py`)

- **`AgentFileStore`** - Abstract async store backing the file-access harness. Implementations expose `write_file`, `read_file`, `delete_file`, `list_files`, `file_exists`, `search_files`, and `create_directory` over forward-slash relative paths.
- **`InMemoryAgentFileStore`** - Dict-backed store suitable for tests and lightweight scenarios.
- **`FileSystemAgentFileStore`** - Disk-backed store rooted under a configurable directory. Enforces relative-path normalization, root containment, and rejects symlink/reparse-point segments to prevent escape.
- **`FileSearchResult`** / **`FileSearchMatch`** - `SerializationMixin` DTOs returned by `search_files`, carrying the matching file name, a context snippet, and the matching lines with 1-based line numbers.
- **`FileAccessProvider`** - `ContextProvider` that adds shared file-access tools (`file_access_save_file`, `file_access_read_file`, `file_access_delete_file`, `file_access_list_files`, `file_access_search_files`) plus default usage instructions to each invocation. Unlike `MemoryContextProvider`, the store is intentionally shared across sessions and agents.

### Workflows (`_workflows/`)

- **`Workflow`** - Graph-based workflow definition
- **`WorkflowBuilder`** - Fluent API for building workflows, including explicit
  `output_from` / `intermediate_output_from` selection for caller-facing emissions. `output_from`
  is an allow-list for **Workflow Output**; unselected executor payloads are hidden unless
  `intermediate_output_from` selects them as **Intermediate Output**. Use `output_from="all"` for
  explicit all-output behavior and `intermediate_output_from="all_other"` for visible progress from
  every output-capable executor not selected by `output_from`.
- **`WorkflowRunResult`** - Non-streaming workflow result with Workflow Output `get_outputs()`
  and Intermediate Output `get_intermediate_outputs()` accessors
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
        return ChatResponse(messages=[Message(role="assistant", contents=["Hi!"])])

    async def _inner_get_streaming_response(self, *, messages, options, **kwargs):
        yield ChatResponseUpdate(...)
```
