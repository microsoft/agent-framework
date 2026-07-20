# MCP Hosting Helpers (`agent-framework-hosting-mcp`)

Side-effect-free adapters and conversion helpers for hosting Agent Framework
agents and workflows through the native MCP SDK.

## Public API

- `MCPAgentTool(target, ...)` generates one native MCP `Tool` from an agent,
  converts and executes calls, and optionally persists sessions through an
  existing `AgentState`.
- `MCPWorkflowTool(target, ...)` derives one native MCP `Tool` from a workflow's
  single start-executor input type and converts completed workflow outputs.
- `mcp_to_run(arguments, *, argument_name="task",
  chat_option_arguments=())` converts MCP tool arguments to `AgentRunArgs` and
  copies only explicitly selected arguments into chat options.
- `mcp_from_run(result)` converts an Agent Framework response or message to MCP
  `ContentBlock` values.

## Boundary

This package does not provide a server, routes, transport lifecycle,
authentication, authorization, session-key policy, concurrency policy, or
outbound delivery. Applications compose the adapter and conversion helpers
with native MCP SDK constructs.

`MCPAgentTool` owns only the schema for its single generated agent tool. It
does not register that schema with a server. Applications call
`await adapter.list_tools()` and `await adapter.call_tool(...)` from native MCP
handlers.

`MCPWorkflowTool` owns only the schema derived from the start executor. It
requires exactly one input type. Workflow factories and continuation policy
remain application-owned. Pending external-input requests raise because the
adapter does not own a human-in-the-loop continuation contract.

When configured with `AgentState`, the adapter performs session get/run/set.
Applications still derive and authorize the session identifier and serialize
concurrent calls for the same session.

MCP tool arguments are JSON-only and have no native multimodal content-block
union. Do not add a package-owned JSON convention for image or audio input.

`mcp_from_run(...)` intentionally returns a flat content block list. It
preserves content-level metadata, while applications own MCP result-level
metadata and structured content.

The helper targets `CallToolResult.content`. Do not add sampling-only
`ToolUseContent` to its output; MCP sampling has a separate response content
union.

`CallToolResult` is a single final result. Streamable HTTP transports MCP
messages rather than partial result content; progress notifications and
experimental tasks remain application-owned protocol concerns.
