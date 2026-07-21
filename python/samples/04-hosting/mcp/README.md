# MCP hosting with native SDK constructs

An MCP server that exposes tools must handle `tools/list` and `tools/call`.
There are two common ways to build that:

1. Implement the list and call handlers directly. The application defines each
   native tool schema, validates or parses its arguments, routes the selected
   tool name, and returns its result.
2. Declare callable tools and let a higher-level server generate the list and
   call handlers from those declarations. FastMCP follows this model by deriving
   tool schemas and argument parsing from Python function signatures.

Choose between them based on the other MCP features you want to expose and how
much control you need over the server, schema, validation, lifecycle, and
transport. Hosting one Agent Framework agent or workflow usually exposes only
one MCP tool, so either model remains small. A directly implemented
`call_tool` handler needs little routing logic when it has only one supported
tool name.

Both approaches use the same two protocol-boundary functions from
`agent-framework-hosting-mcp`:

- `mcp_to_run(...)` converts validated MCP tool arguments into Agent Framework
  messages and selected chat options.
- `mcp_from_run(...)` converts a completed Agent Framework response into native
  MCP result content blocks.

These functions are the smallest Agent Framework integration boundary. The
later samples add optional helpers that derive tool schemas, execute agents or
workflows, and manage Agent Framework conversation state.

## Samples

### 1. Manual low-level server

[`manual_app.py`](manual_app.py) shows the complete boundary directly. It
defines the native MCP `Tool`, registers low-level `list_tools` and `call_tool`
handlers, calls `mcp_to_run(...)`, runs the agent, and calls
`mcp_from_run(...)`.

Use this when the application needs full control over a custom MCP contract.

```bash
uv run manual_app.py
```

### 2. FastMCP server

[`fastmcp_app.py`](fastmcp_app.py) keeps the same two conversion functions but
replaces the low-level server setup with FastMCP. FastMCP derives and validates
the tool schema from the decorated `run_agent(...)` function and owns the
streamable HTTP server.

Use this when a normal Python function signature fully describes the MCP tool.
FastMCP keeps its generated schema and argument parsing aligned.

```bash
uv run fastmcp_app.py
```

### 3. Agent-derived tool

[`agent_app.py`](agent_app.py) adds `AgentMCPTool` to the low-level server. The adapter
derives the native tool name and description from the agent, owns the configured
argument schema, runs the agent, and applies the same conversion boundary.

Use this when one Agent Framework agent should be represented as one generated
MCP tool. Unlike the FastMCP sample, this adapter derives the contract from the
agent and its adapter configuration rather than a decorated function signature.

```bash
uv run agent_app.py
```

### 4. Session-aware agent

[`session_app.py`](session_app.py) builds on `AgentMCPTool` with `AgentState`.
It loads and stores an `AgentSession` using an opaque, application-defined
`session_id` and serializes calls per ID in-process.

Reusing the same ID continues and updates one conversation. This is not
`previous_response_id`-style branching. An application that needs forks should
define separate source and destination IDs, copy the source session, and store
the completed turn under the destination ID.

```bash
uv run session_app.py
```

### 5. Workflow-derived tool

[`workflow_app.py`](workflow_app.py) uses `WorkflowMCPTool` to derive the tool
schema from the workflow start executor's single input type. Dataclass or
Pydantic fields become top-level MCP arguments; primitive inputs are wrapped in
one configurable argument.

The sample uses a `WorkflowState` factory with `cache_target=False` so each MCP
call receives a fresh workflow instance. Checkpoint and human-in-the-loop
continuation remain application-owned contracts.

```bash
uv run workflow_app.py
```

## Concept summary

| Concept | Responsibility | Used by |
|---|---|---|
| `mcp_to_run(...)` | Converts validated MCP arguments into Agent Framework messages and selected chat options. | `manual_app.py`, `fastmcp_app.py` |
| `mcp_from_run(...)` | Converts a completed agent response into MCP result content blocks. | `manual_app.py`, `fastmcp_app.py` |
| `AgentMCPTool` | Derives one native MCP tool from an agent and keeps schema, execution, and conversion aligned. | `agent_app.py`, `session_app.py` |
| `WorkflowMCPTool` | Derives one native MCP tool from a workflow start executor and converts workflow outputs. | `workflow_app.py` |

## Run

The agent samples require Microsoft Foundry configuration:

```bash
export FOUNDRY_PROJECT_ENDPOINT=https://<your-project>.services.ai.azure.com
export FOUNDRY_MODEL=gpt-5-nano
az login
```

Run one sample, connect an MCP client to `http://127.0.0.1:8000/mcp`, and invoke
its tool. The agent tools accept a `task` string and optionally
`reasoning_effort` with `low`, `medium`, or `high`.

Each entry point declares its complete Agent Framework and third-party
dependency set using PEP 723 inline script metadata.

## Common behavior

- **No framework choice:** the package does not select FastMCP, Starlette,
  Uvicorn, stdio, or streamable HTTP.
- **Chat options:** only explicitly selected MCP arguments are passed to the
  model client. The samples expose `reasoning_effort` as an example, but any option
  valid for the agent can be exposed.
- **Input shape:** MCP tool arguments are JSON objects and do not define native
  multimodal input content blocks. The samples do not present an
  application-specific image schema as protocol behavior.
- **Streaming:** streamable HTTP can carry multiple MCP messages, but a tool
  call still produces one final `CallToolResult`. Progress notifications and
  experimental deferred tasks remain application-owned protocol features.
- **Authentication:** the local endpoints are intentionally unauthenticated.
  MCP transport session identifiers are not user authorization. Production
  servers must authenticate and authorize before loading tenant or user state.
- **Errors:** conversion, model, workflow, and protocol errors propagate to the
  MCP SDK rather than becoming success-shaped tool output.
