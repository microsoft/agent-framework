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
- **`ServiceSessionId`** - Mapping alias for structured service-owned continuation handles used in `AgentSession.service_session_id`
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
- **`SkillScriptArgumentParser`** - Public type alias for an optional callable `(raw args: dict | list[str] | str | None) -> dict | None` that converts the raw `args` value before an `InlineSkillScript` runs (applied before the inline list-args guard). It is an opt-in customization hook (port of .NET PR #6498) that lets callers support backends sending tool-call arguments in a non-conforming shape (e.g. vLLM JSON strings). The output is constrained to a `dict` (named keyword arguments) or `None`, because inline scripts bind arguments by keyword name. Supply it via the `argument_parser=` constructor arg on `InlineSkillScript`, `InlineSkill` (default for scripts added via `@skill.script`), or `ClassSkill` (default for scripts discovered via `@ClassSkill.script`). When `None` (the default), the raw value is used unchanged. File-based scripts are unaffected (their runner owns arg handling).
- **`SkillsProvider`** - Context provider (extends `ContextProvider`) that discovers file-based skills from `SKILL.md` files and/or accepts code-defined `Skill` instances. Follows progressive disclosure: advertise → load → read resources / run scripts. All three tools it exposes (`load_skill`, `read_skill_resource`, `run_skill_script`) are registered with `approval_mode="always_require"`, so every skill operation needs approval. To run unattended, pass one of the static auto-approval rules to `ToolApprovalMiddleware` (via `auto_approval_rules`): `SkillsProvider.read_only_tools_auto_approval_rule` approves only the read-only tools (`load_skill`, `read_skill_resource`) while still prompting for `run_skill_script`, and `SkillsProvider.all_tools_auto_approval_rule` approves every skill tool including script execution. Both rules reject any call carrying a `server_label` so they stay scoped to this provider's local tools and never auto-approve a same-named hosted tool. The tool names are also exposed as class constants (`LOAD_SKILL_TOOL_NAME`, `READ_SKILL_RESOURCE_TOOL_NAME`, `RUN_SKILL_SCRIPT_TOOL_NAME`).
- **`SkillsSource` decorators** - Skill sources are composable: `SkillsSource` is the abstract base, with concrete sources (`InMemorySkillsSource`, `FileSkillsSource`, `MCPSkillsSource`) and decorators that wrap an inner source — `AggregatingSkillsSource` (concatenate several sources), `FilteringSkillsSource` (predicate filter), `DeduplicatingSkillsSource` (first-wins by name), and `CachingSkillsSource` (cache the inner source's skills list). `DelegatingSkillsSource` is the abstract base for decorators. **Caching lives in the source pipeline, not the provider**: `SkillsProvider` wraps its resolved source in a `CachingSkillsSource` by default (so expensive filesystem/network discovery runs once and is reused), and rebuilds instructions/tools from the cached skills each run. Pass `disable_caching=True` to `SkillsProvider(...)` / `SkillsProvider.from_paths(...)` to skip the wrapping and re-query the source on every run. `CachingSkillsSource` shares a single in-flight fetch across concurrent callers and resets its cache on failure so the next call retries.

### Model Context Protocol (`_mcp.py`)

- **`MCPTool`** - Base wrapper that owns the MCP `ClientSession` and exposes the remote server's tools as `FunctionTool`s.
- **`MCPStdioTool`** / **`MCPStreamableHTTPTool`** / **`MCPWebsocketTool`** - Transport-specific subclasses.
- **Argument allowlist (`_prepare_call_kwargs`)** - Before each `tools/call`, kwargs are filtered to an **allowlist** built from the tool's declared parameters (`inputSchema.properties`) plus any user-configured extras. Framework runtime kwargs injected through the function-invocation pipeline (e.g. `thread`, `conversation_id`, `chat_options`, `options`, `response_format`) are stripped by default rather than forwarded. A tool that declares no usable `properties` (including schemas with `additionalProperties: true`) forwards only the configured extras. The `_MCP_FRAMEWORK_DENYLIST` is a safety net for framework-named params a server *declares* in its schema (those are dropped); names explicitly opted in via `additional_tool_argument_names` always win. The reserved `_meta` key is never forwarded as an argument; trusted caller/runtime `_meta` is validated as MCP request metadata, model-supplied `_meta` is discarded in generated MCP functions, and metadata precedence is caller/runtime < OpenTelemetry < tools/list metadata.
- **`allowed_tools`** (constructor arg on all `MCPTool` subclasses) - Restricts exposed MCP tools by raw remote MCP tool identity. Prefixed local names remain accepted only when the raw remote name already matches its normalized form; normalized/local aliases do not authorize a different raw remote name. If multiple raw remote tool names map to the same local function name, tool loading raises `ToolExecutionException` instead of first-one-wins shadowing.
- **`additional_tool_argument_names`** (constructor arg on all `MCPTool` subclasses) - Opt extra argument names back into the allowlist. Accepts a `Sequence[str]` (applied to every tool) or a `Mapping[str, Sequence[str]]` keyed by **remote tool name**, where the reserved key `"*"` denotes global extras. It is configured only in user code at construction; there is **no per-call/runtime override**, so a model-issued tool call cannot change which names pass through. To use a server that accepts `additionalProperties: true`, list the extra names here and then either (1) manually extend that tool's `inputSchema` (via the `.functions` list after connecting) so the model is prompted to supply them, or (2) supply the values yourself via `function_invocation_kwargs`. If a normal forwarded argument name is supplied by both the model and `function_invocation_kwargs`, the model-supplied value wins; `_meta` is the exception and only trusted runtime/caller metadata is used.
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

- **`AgentFileStore`** - Abstract async store backing the file-access harness. Implementations expose `write`, `read`, `delete`, `list_children`, `file_exists`, `search`, and `create_directory` over forward-slash relative paths. `list_children` returns the direct children (files and subdirectories, subdirectories first) as `FileStoreEntry` instances; `search` accepts a keyword-only `recursive` flag (default `False`) and, when `recursive=True`, walks all descendants and returns `file_name` values relative to the search directory.
- **`InMemoryAgentFileStore`** - Dict-backed store suitable for tests and lightweight scenarios.
- **`FileSystemAgentFileStore`** - Disk-backed store rooted under a configurable directory. Enforces relative-path normalization, root containment, and rejects symlink/reparse-point segments to prevent escape.
- **`FileSearchResult`** / **`FileSearchMatch`** - `SerializationMixin` DTOs returned by `search`, carrying the matching file name, a context snippet, and the matching lines with 1-based line numbers.
- **`FileStoreEntry`** - `SerializationMixin` DTO returned by `list_children`, carrying an entry `name` and `type` (`"file"` or `"directory"`).
- **`FileAccessProvider`** - `ContextProvider` that adds shared file-access tools (`file_access_write`, `file_access_read`, `file_access_delete`, `file_access_ls`, `file_access_grep`, `file_access_replace`, `file_access_replace_lines`) plus default usage instructions to each invocation. `file_access_ls` enumerates direct children (both files and subdirectories) as `{name, type}` entries with an optional `glob_pattern`, so the agent can walk the tree level by level; `file_access_grep` searches recursively from an optional base `directory` and returns relative `file_name` paths, scoped via an `fnmatch` `glob_pattern` (where `*` crosses `/`, e.g. `*.md`, `reports/*`). `file_access_replace` substitutes `old_string` with `new_string` (failing if not found, or if multiple matches and `replace_all` is false); `file_access_replace_lines` replaces whole 1-based lines with literal text (each `new_line` includes its own trailing newline; an empty `new_line` deletes the line, including its line break). All tools are registered with `approval_mode="always_require"` by default, so every file operation needs host approval. Pass `disable_write_tools=True` to advertise only the read-only tools. To run unattended you can disable approval at the source with `disable_readonly_tool_approval=True` (read, ls, grep) and/or `disable_write_tool_approval=True` (write, delete, replace, replace_lines), which register the affected tools with `approval_mode="never_require"`; alternatively, keep approval on and pass one of the static auto-approval rules to `ToolApprovalMiddleware` (via `auto_approval_rules`): `FileAccessProvider.read_only_tools_auto_approval_rule` approves only the read-only tools (read, ls, grep), while `FileAccessProvider.all_tools_auto_approval_rule` approves every file-access tool including the write tools. Both rules reject any call carrying a `server_label` so they stay scoped to this provider's local tools and never auto-approve a same-named hosted tool. The tool names are also exposed as class constants (`WRITE_TOOL_NAME`, `READ_TOOL_NAME`, `DELETE_TOOL_NAME`, `LS_TOOL_NAME`, `GREP_TOOL_NAME`, `REPLACE_TOOL_NAME`, `REPLACE_LINES_TOOL_NAME`). Unlike `MemoryContextProvider`, the store is intentionally shared across sessions and agents.

### File Memory Harness (`_harness/_file_memory.py`)

- **`FileMemoryProvider`** - `ContextProvider` that gives an agent a session-scoped, file-based memory backed by the same `AgentFileStore` abstraction. Adds tools (`file_memory_write`, `file_memory_read`, `file_memory_delete`, `file_memory_ls`, `file_memory_grep`, `file_memory_replace`, `file_memory_replace_lines`) plus default usage instructions. Port of the .NET `FileMemoryProvider`.
- **Scoping** - Memories are isolated per session by default: each session writes under a working folder derived from `context.session_id`. Pass an explicit `scope` (e.g. a user id) to group memories across sessions, mirroring `FoundryMemoryProvider`'s `scope` arg.
- **Descriptions & index** - `file_memory_write` accepts an optional `description`, stored in a companion `<stem>_description.md` sidecar. After each write/delete the provider rebuilds a capped (50-entry) `memories.md` index, and `before_run` injects that index as a `user` context message so the model knows what memories exist. Sidecars and the index are internal files hidden from `file_memory_ls`/`file_memory_grep` and rejected as write targets.
- **`DEFAULT_FILE_MEMORY_SOURCE_ID`** / **`DEFAULT_FILE_MEMORY_INSTRUCTIONS`** - Public defaults for the provider's source id and instruction banner.
- **Harness wiring** - `create_harness_agent` includes both `FileMemoryProvider` and `FileAccessProvider` by default. Disable via `disable_file_memory` / `disable_file_access`; override the backing store via `file_memory_store` / `file_access_store`. When no store is supplied, defaults are `FileSystemAgentFileStore` rooted at `{cwd}/agent-file-memory` (memory) and `{cwd}/working` (access), mirroring the .NET `HarnessAgent`.

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
### Agent Loop (`_harness/_loop.py`)

- **`AgentLoopMiddleware`** - `AgentMiddleware` that re-runs an agent in a loop by calling `call_next()` repeatedly (the pipeline re-reads `context.messages` each time). One configurable class covers two patterns: a required user `should_continue` predicate (sync or async, the first positional/keyword arg), and a chat-client judge built via the `.with_judge(...)` factory (a second chat client decides whether the original request was answered; loops while it is *not*, using a `JudgeVerdict` structured-output response — internally just an async `should_continue` predicate). The constructor covers the predicate pattern directly; only the judge has a convenience classmethod factory (`.with_judge(judge_client, ...)`) that forwards to `__init__`. Supports both streaming and non-streaming runs. By default a non-streaming run returns an aggregated `AgentResponse` containing every iteration's messages plus the injected `next_message` "nudge" messages (as `user` messages); set `return_final_only=True` to return only the last iteration's response. Streaming runs always yield each iteration's updates and emit the injected nudge messages as `user` updates between iterations (the `return_final_only` flag has no effect on streaming, and the final response reflects the last iteration; `MiddlewareTermination` is handled cleanly). `should_continue` is required; other constructor args are optional: `max_iterations` (safety cap; defaults to `DEFAULT_MAX_ITERATIONS`=10, explicit `None`→unbounded, positive int caps; `.with_judge` uses `DEFAULT_JUDGE_MAX_ITERATIONS`=5 as its default), `next_message` (defaults to a short "continue" nudge), `return_final_only`, and `additional_instructions` (an extra `system` message injected ahead of the input before the agent runs — becomes part of the original messages so it survives `fresh_context` resets and persists via a session). The judge is configured only through `.with_judge` (`judge_client`/`instructions`/`criteria`), not the constructor, and its `reasoning` is fed back to the agent as the next iteration's input; the judge forwards the original request messages and the agent's latest response messages verbatim so multi-modal content is preserved. `criteria` (a `list[str]`) is both injected as the agent's `additional_instructions` and rendered into the judge instructions wherever the `{{criteria}}` placeholder (`CRITERIA_PLACEHOLDER`) appears (`DEFAULT_JUDGE_INSTRUCTIONS` ends with it; custom `instructions` may include it, and it is stripped when no criteria are given). The `should_continue`/`next_message` callables are invoked with keyword args (`iteration`, `last_result`, `messages`, `original_messages`, `session`, `agent`, `progress`, `feedback`) and may be sync or async; declare only what you need plus `**kwargs`. `should_continue` may return a plain `bool` or a `(bool, str | None)` tuple whose second item is feedback surfaced to `next_message`/`record_feedback` via the `feedback` kwarg (the judge uses this to relay its `reasoning`). Stop precedence per iteration is `max_iterations` → `should_continue`, evaluated before `record_feedback` so the feedback is available to it.
  - **Feedback tracking** - `record_feedback` captures a per-iteration progress entry (called with the loop kwargs; if it returns a truthy string the entry is appended, otherwise the agent's response text is used as the fallback entry). The accumulated log is exposed to every callback via the `progress` keyword (a per-iteration copy of prior entries) and, when `inject_progress=True` (default), injected into the next iteration's input as a `user` message (the full log without a session, only the latest entry with a session to avoid duplicating history). `fresh_context=True` restarts each iteration from the original task plus the progress log; when a session is attached it is snapshotted (`to_dict()`) before the loop and restored (`from_dict` + field copy) between iterations so the local transcript and any service-side conversation id reset too (in-loop working-state is discarded, pre-loop state preserved, continuity carried only by the progress log).
- **`todos_remaining(*, looping_modes=None)`** / **`todos_remaining_message`** - Helper factories for todo-driven loops (the Python counterpart of .NET's `TodoCompletionLoopEvaluator`), designed for `create_harness_agent` but usable with any agent that registers a `TodoProvider` via `context_providers`. They resolve the `TodoProvider`/`AgentModeProvider` from the *running agent* (`agent.context_providers`, via `_resolve_context_provider`) rather than taking the provider as an argument, so they can be wired directly into `loop_should_continue`/`loop_next_message`. `todos_remaining` returns a `should_continue` predicate that loops while any todo is open; pass `looping_modes=[...]` to gate looping to specific operating modes (case-insensitive; honors the `AgentModeProvider`'s `source_id`/`available_modes`), `looping_modes=None` (default) applies in every mode, and an empty sequence raises `ValueError`. `todos_remaining_message` is a `next_message` callable that lists the still-open todo titles and tells the agent to finish them, returning `None` when the session/agent/provider is unavailable or nothing is open (in which case the middleware's default `None` handling applies: reuse the previous iteration's messages verbatim under the default `fresh_context=False`, or `DEFAULT_NEXT_MESSAGE` only when `fresh_context=True`).
- **`background_tasks_running()`** / **`background_tasks_running_message`** - Helper factories for background-agent-driven loops, mirroring the `todos_remaining` pair. They resolve the `BackgroundAgentsProvider` from the *running agent* (`agent.context_providers`, via `_resolve_context_provider`) rather than taking the provider as an argument, so they can be wired directly into `create_harness_agent`'s `loop_should_continue`/`loop_next_message`. `background_tasks_running` returns a `should_continue` predicate that loops while the provider's persisted state shows any task with `status == RUNNING` (pair it with `max_iterations` so the loop is bounded even if a task's persisted status is never refreshed). `background_tasks_running_message` is a `next_message` callable that lists the still-running tasks (`#<id> (<agent_name>): <description>`) and tells the agent to wait for them to finish and retrieve their results, returning `None` when the session/agent/provider is unavailable or no task is running.
  - **Approval escape hatch** - `_has_pending_approval_request(result)` checks whether an iteration's response carries a pending tool-approval request (any content with `type == "function_approval_request"`). Both the streaming and non-streaming loops stop and return that response to the caller *before* evaluating `should_continue`/`max_iterations` or injecting `next_message`, so the loop is HITL-safe even when wrapped outermost around a `ToolApprovalMiddleware` (mirrors the C# `LoopAgent`'s `HasPendingApprovalRequests`).
  - **Harness integration** - `create_harness_agent` enables the loop when a `loop_should_continue` callable is passed; it prepends `AgentLoopMiddleware(loop_should_continue, max_iterations=loop_max_iterations, next_message=loop_next_message)` ahead of `ToolApprovalMiddleware` so the loop is the outermost middleware (each iteration is a full agent run including tool approval, and the escape hatch hands pending approvals back to the caller). `loop_next_message` and `loop_max_iterations` only take effect together with `loop_should_continue` (with no `loop_should_continue` there is no loop, so they are ignored); `loop_max_iterations` defaults to the loop's default cap (`None` → unbounded).

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
