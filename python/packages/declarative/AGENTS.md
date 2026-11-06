# Declarative Package (agent-framework-declarative)

YAML/JSON-based declarative agent and workflow definitions.

## Main Classes

- **`AgentFactory`** - Creates agents from declarative definitions
- **`WorkflowFactory`** - Creates workflows from declarative definitions
- **`WorkflowState`** - Standalone state management and expression evaluation; factory-created workflows use the internal, checkpoint-backed `DeclarativeWorkflowState` instead
- **`ProviderTypeMapping`** - Maps provider types to implementations
- **`HttpRequestHandler`** / **`DefaultHttpRequestHandler`** - Pluggable HTTP transport for the `HttpRequestAction` declarative action (configured via `WorkflowFactory(http_request_handler=...)`)
- **`MCPToolHandler`** / **`DefaultMCPToolHandler`** - Pluggable MCP transport for the `InvokeMcpTool` declarative action (configured via `WorkflowFactory(mcp_tool_handler=...)`)
- **`DeclarativeLoaderError`** / **`ProviderLookupError`** / **`DeclarativeWorkflowError`** / **`DeclarativeActionError`** - Error types

Both state classes validate object attribute names but leave dictionary keys unchanged.

`DefaultHttpRequestHandler(max_response_body_bytes=...)` defaults to a 10 MiB
wire and decoded-stage body limit, including redirect and authentication responses.
It supports identity, gzip, and deflate, rejects unsupported or incomplete encodings,
and closes response streams without closing caller-owned clients.
HTTPX is constrained to the 0.27 and 0.28 series; focused CI checks both
series because response caching and default-header integration use its internals.

## MCP Handler Lifetimes

`DefaultMCPToolHandler` creates a fresh tool/session for every invocation, including
`tools/list`, with or without a `client_provider`. A provider may return `None` or a
shared HTTP client without sharing protocol sessions. Invocation cleanup closes
the session and any internally owned HTTP client, never caller-owned HTTP clients.
The handler forwards its configurable `max_discovery_pages` and `max_discovery_items`
limits to every internally created `MCPStreamableHTTPTool`.
The handler has no cache, `aclose()`, or async context manager. It accepts the
legacy `cache_max_size` parameter as a deprecated no-op for compatibility:
positive values emit `DeprecationWarning`, non-positive values raise `ValueError`,
and omission emits no warning. The parameter never enables session sharing.
Hosts own admission, deadlines, cancellation, and shutdown of active calls; cancel
and await them before closing any borrowed HTTP client.

Provider, connection, discovery, and transport failures propagate and fail the
action, including after approval. Remote tool error responses remain
`MCPToolResult(is_error=True)`; executors do not convert raised exceptions into results.

Per-invocation sessions add connection overhead and intentionally lose implicit
server session continuity across calls, approval waits, and checkpoint resumes.
Applications requiring continuity must use explicit remote state handles or an
explicitly scoped custom `MCPToolHandler`. No Core workflow scope or checkpoint
migration is involved.

## MCP Approval Context

`InvokeMcpToolActionExecutor` binds evaluated headers to each request with a
workflow-local HMAC key held separately in trusted host checkpoint state.
Only the opaque binding and header names enter the approval payload; raw headers
are not checkpointed. Changed or unverifiable headers produce a replacement
request for the same pinned operation, with a fresh request ID and no dispatch.
Fresh executors verify unchanged approvals using the checkpointed key; legacy
requests or missing verification state require reapproval for non-empty headers.
Custom handlers remain responsible for identity changes
in credentials they resolve outside the action's headers.

`InvokeAzureAgent` uses Core's executor-ready kwargs conversion for both modern
and legacy state, without copying workflow/client kwargs into additional tool
arguments. Explicit caller tool arguments in options are preserved.

## External Input Handling

- **`ExternalInputRequest`** / **`ExternalInputResponse`** - Human-in-the-loop support
- **`AgentExternalInputRequest`** / **`AgentExternalInputResponse`** - Agent-level input requests

## Usage

```python
from agent_framework.declarative import AgentFactory, WorkflowFactory

# Create agent from YAML file
agent_factory = AgentFactory()
agent = agent_factory.create_agent_from_yaml_path("agent.yaml")

# Create workflow from YAML file
workflow_factory = WorkflowFactory()
workflow = workflow_factory.create_workflow_from_yaml_path("workflow.yaml")
```

## Import Path

```python
from agent_framework.declarative import AgentFactory, WorkflowFactory
# or directly:
from agent_framework_declarative import AgentFactory
```
