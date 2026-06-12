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
- **`AgentContext`** / **`ChatContext`** / **`FunctionInvocationContext`** - Context objects passed through middleware. A tool can declare a `FunctionInvocationContext` parameter to receive it; `context.tools` is the live, mutable tools list for the run, and `context.add_tools(...)` / `context.remove_tools(...)` enable progressive tool exposure (changes apply on the next function-calling iteration).

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

### Model Context Protocol (`_mcp.py`)

- **`MCPTool`** - Base wrapper that owns the MCP `ClientSession` and exposes the remote server's tools as `FunctionTool`s.
- **`MCPStdioTool`** / **`MCPStreamableHTTPTool`** / **`MCPWebsocketTool`** - Transport-specific subclasses.
- **Argument allowlist (`_prepare_call_kwargs`)** - Before each `tools/call`, kwargs are filtered to an **allowlist** built from the tool's declared parameters (`inputSchema.properties`) plus any user-configured extras. Framework runtime kwargs injected through the function-invocation pipeline (e.g. `thread`, `conversation_id`, `chat_options`, `options`, `response_format`) are stripped by default rather than forwarded. A tool that declares no usable `properties` (including schemas with `additionalProperties: true`) forwards only the configured extras. The `_MCP_FRAMEWORK_DENYLIST` is a safety net for framework-named params a server *declares* in its schema (those are dropped); names explicitly opted in via `additional_tool_argument_names` always win. The reserved `_meta` key is extracted as MCP request metadata, never forwarded as an argument.
- **`additional_tool_argument_names`** (constructor arg on all `MCPTool` subclasses) - Opt extra argument names back into the allowlist. Accepts a `Sequence[str]` (applied to every tool) or a `Mapping[str, Sequence[str]]` keyed by **remote tool name**, where the reserved key `"*"` denotes global extras. It is configured only in user code at construction; there is **no per-call/runtime override**, so a model-issued tool call cannot change which names pass through. To use a server that accepts `additionalProperties: true`, list the extra names here and then either (1) manually extend that tool's `inputSchema` (via the `.functions` list after connecting) so the model is prompted to supply them, or (2) supply the values yourself via `function_invocation_kwargs`. If a name is supplied by both the model and `function_invocation_kwargs`, the model-supplied value wins.
- **Sampling guardrails** (`sampling_callback`) - Passing `client=` advertises `SamplingCapability` so the server can send `sampling/createMessage`. Because remote servers are untrusted (confused-deputy risk), the default `sampling_callback` is **deny-by-default** and applies, in order: a per-session rate limit (`sampling_max_requests`, default `_DEFAULT_SAMPLING_MAX_REQUESTS`), an approval gate (`sampling_approval_callback`), and a `maxTokens` cap (`sampling_max_tokens`, default `_DEFAULT_SAMPLING_MAX_TOKENS`). The approval callback (constructor arg on all subclasses; exported type alias `SamplingApprovalCallback`) receives the raw `CreateMessageRequestParams`, may be sync or async, and must return truthy to approve. When it is `None` (the default) every sampling request is denied; pass `lambda params: True` to restore legacy auto-approve as an explicit opt-in. Requests and denials are logged at WARNING (content is not logged). The per-session counter resets in `_reset_session_state`.
- **`MCPTaskOptions`** (experimental, `MCP_LONG_RUNNING_TASKS` feature, **frozen**) - Per-tool-instance options controlling the SEP-2663 long-running task lifecycle. When the server advertises a tool with `execution.taskSupport == "required"`, `MCPTool.call_tool` transparently routes through `call_tool_as_task`, which sends an augmented `tools/call`, polls `tasks/get` until terminal, and reinterprets `tasks/result` as a normal `CallToolResult`. Instances are immutable; replace via `MCPTool.task_options = MCPTaskOptions(...)`. Fields:
  - `default_ttl: timedelta | None` — forwarded to the server as `params.task.ttl` (milliseconds). When `None`, the server's default applies.
  - `cancel_remote_task_on_local_cancellation: bool = True` — only gates the `CancelledError` path. Abandonment paths (see below) always cancel.
  - `max_task_wait: timedelta | None` — client-side deadline for the whole post-create lifecycle (poll + result fetch). When exceeded, raises `ToolExecutionException` and fires a best-effort `tasks/cancel`. `None` (default) means no client-side bound. Bounds sleeps, sends, AND reconnects via `asyncio.wait_for`.
- **Permissive fallback**: servers that ignore the augmentation (return `CallToolResult` directly) or reject the unknown `task` field with `METHOD_NOT_FOUND` / `INVALID_PARAMS` fall back to the plain `session.call_tool(...)` path so legacy servers keep working. An unparseable success response (server accepted the augmented call but returned a payload that is neither `CreateTaskResult` nor `CallToolResult`) **does not** fall back — it raises `ToolExecutionException` to avoid double-executing a side-effecting tool.
- **Submit-vs-track reconnect policy**: a dropped connection before a `task_id` is known raises `ToolExecutionException("connection lost; task state unknown")` without re-issuing the augmented `tools/call`, so a server that accepted the request but lost the response cannot be made to start the same operation twice; once a `task_id` exists, `tasks/get` / `tasks/result` reconnect once and retry against the same id (a shared `_send_with_one_reconnect` helper).
- **Cancel-on-abandonment vs terminal failure**: any path where the remote task may still be running (max-wait exceeded, hard `McpError` in poll, malformed `tasks/get`, second connection loss in poll/fetch, reconnect failure) fires best-effort `tasks/cancel` before raising. Terminal failures (`failed`/`cancelled`/`input_required` server-side, `completed+isError`, malformed `tasks/result` after server completed) do **not** cancel — the server is already done. `_MCPTaskAbandoned` is the private marker distinguishing the two.
- **Transient poll retry**: a slow `tasks/get` that surfaces as `McpError(code=408 REQUEST_TIMEOUT)` is retried (bounded by `max_task_wait`). All other non-connection `McpError`s during poll are treated as abandonment. `tasks/result` does not get transient retry — the server has already completed, so a slow payload fetch is anomalous.

### File Access Harness (`_harness/_file_access.py`)

- **`AgentFileStore`** - Abstract async store backing the file-access harness. Implementations expose `write_file`, `read_file`, `delete_file`, `list_files`, `file_exists`, `search_files`, and `create_directory` over forward-slash relative paths.
- **`InMemoryAgentFileStore`** - Dict-backed store suitable for tests and lightweight scenarios.
- **`FileSystemAgentFileStore`** - Disk-backed store rooted under a configurable directory. Enforces relative-path normalization, root containment, and rejects symlink/reparse-point segments to prevent escape.
- **`FileSearchResult`** / **`FileSearchMatch`** - `SerializationMixin` DTOs returned by `search_files`, carrying the matching file name, a context snippet, and the matching lines with 1-based line numbers.
- **`FileAccessProvider`** - `ContextProvider` that adds shared file-access tools (`file_access_save_file`, `file_access_read_file`, `file_access_delete_file`, `file_access_list_files`, `file_access_search_files`) plus default usage instructions to each invocation. Unlike `MemoryContextProvider`, the store is intentionally shared across sessions and agents.

### Tool Approval Harness (`_harness/_tool_approval.py`)

- **`ToolApprovalMiddleware`** - Experimental opt-in agent middleware that coordinates session-backed approval
  rules, heuristic `auto_approval_rules`, queued approval requests, collected approval responses, and
  streaming/non-streaming approval prompts. Heuristic callbacks receive the underlying `function_call` content.
- **`ToolApprovalRule`** / **`ToolApprovalState`** - Serializable state models for standing approvals and queued
  approval flow. `ToolApprovalRule.arguments is None` means a tool-wide rule; an empty dict `{}` means an exact
  no-argument call for `create_always_approve_tool_with_arguments_response`.
- **`create_always_approve_tool_response`** / **`create_always_approve_tool_with_arguments_response`** - Helpers
  that return normal `function_approval_response` content with `additional_properties` metadata consumed by
  `ToolApprovalMiddleware`. Standing rules for hosted tools include the `server_label` boundary, so same-named tools
  on different hosted servers do not share approvals.
- Mixed tool-call batches use a default .NET-style bypass in the function invocation loop: when a session is
  available, approval requests for known non-approval-required tools are treated as already approved, hidden, stored
  in session state keyed to the visible approval request ids from that batch, and reinjected only when that visible
  approval flow resumes.

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
