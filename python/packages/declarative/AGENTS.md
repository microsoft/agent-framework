# Declarative Package (agent-framework-declarative)

YAML/JSON-based declarative agent and workflow definitions.

## Main Classes

- **`AgentFactory`** - Creates agents from declarative definitions
- **`WorkflowFactory`** - Creates workflows from declarative definitions
- **`WorkflowState`** - State management for declarative workflows
- **`ProviderTypeMapping`** - Maps provider types to implementations
- **`HttpRequestHandler`** / **`DefaultHttpRequestHandler`** - Pluggable HTTP transport for the `HttpRequestAction` declarative action (configured via `WorkflowFactory(http_request_handler=...)`)
- **`MCPToolHandler`** / **`DefaultMCPToolHandler`** - Pluggable MCP transport for the `InvokeMcpTool` declarative action (configured via `WorkflowFactory(mcp_tool_handler=...)`)
- **`DeclarativeLoaderError`** / **`ProviderLookupError`** / **`DeclarativeWorkflowError`** / **`DeclarativeActionError`** - Error types

## MCP Handler Lifetimes

`DefaultMCPToolHandler` caches/coalesces sessions only without a `client_provider`.
With a provider, every invocation (including `tools/list`) gets a fresh tool/session,
even if the provider returns `None` or a shared HTTP client. Invocation cleanup closes
the session and any internally owned fallback client, never caller-owned HTTP clients.
Shutdown waits for active provider-backed invocations to clean up. Calling `aclose()`
from an active invocation's context (including inherited child tasks and cleanup)
raises `RuntimeError` before changing handler state; shutdown must run outside that
context or after invocation completion.

Per-invocation sessions intentionally add connection overhead and lose server
session continuity between invocations;
shared session ownership requires an explicitly scoped custom `MCPToolHandler`.

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
