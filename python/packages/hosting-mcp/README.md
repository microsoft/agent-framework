# agent-framework-hosting-mcp

MCP conversion helpers for app-owned Agent Framework hosting.

The package deliberately does not choose a web framework or wrap the MCP SDK
server lifecycle. It provides two conversion functions and small adapters:

- `mcp_to_run(...)` converts native MCP tool arguments into Agent Framework run
  arguments.
- `mcp_from_run(...)` converts an `AgentResponse` or `Message` into native MCP
  `ContentBlock` values.
- `AgentMCPTool(...)` generates the native `Tool` definition from an agent and
  keeps listing, parsing, execution, result conversion, and optional
  `AgentState` session persistence aligned.
- `WorkflowMCPTool(...)` generates the native `Tool` definition from a
  workflow's start-executor input type and converts completed workflow outputs.

Application code keeps ownership of the MCP SDK's `Server`, handler
registration, request context, transport, session-key policy, authentication,
authorization, and deployment.

For direct conversion, the argument name is part of the app-owned MCP tool
contract. Define it once and use the same value in both the native tool schema
and `mcp_to_run(...)`:

```python
from jsonschema import validate
from mcp.types import Tool

from agent_framework_hosting_mcp import mcp_to_run

agent_input_argument = "task"
chat_option_arguments = {
    "reasoning_effort": {
        "type": "string",
        "enum": ["low", "medium", "high"],
    },
}

tool = Tool(
    name="run_agent",
    input_schema={
        "type": "object",
        "properties": {
            agent_input_argument: {"type": "string"},
            **chat_option_arguments,
        },
        "required": [agent_input_argument],
    },
)
validate(instance=arguments, schema=tool.input_schema)
run = mcp_to_run(
    arguments,
    argument_name=agent_input_argument,
    chat_option_arguments=chat_option_arguments,
)
```

Only names listed in `chat_option_arguments` are copied to `run["options"]`;
other MCP arguments remain available in the message's raw representation but
are not forwarded to the model client. Applications using the conversion
helper directly must validate arguments against their tool schema before
conversion. Declaring a schema does not enforce it in the low-level MCP server.

For an agent exposed as one MCP tool, use the adapter so the schema and
conversion cannot drift:

```python
from mcp import types
from mcp.server import Server, ServerRequestContext

from agent_framework_hosting_mcp import AgentMCPTool

agent_tool = AgentMCPTool(
    agent,
    name="run_agent",
    argument_description="The request for the hosted agent.",
    parameters={"audience": {"type": "string"}},
    chat_option_parameters={
        "reasoning_effort": {
            "type": "string",
            "enum": ["low", "medium", "high"],
        }
    },
)


async def list_tools(
    _ctx: ServerRequestContext[dict[str, object]],
    _params: types.PaginatedRequestParams | None,
) -> types.ListToolsResult:
    return await agent_tool.list_tools()


async def call_tool(
    _ctx: ServerRequestContext[dict[str, object]],
    params: types.CallToolRequestParams,
) -> types.CallToolResult:
    return await agent_tool.call_tool(params.name, params.arguments)


server = Server("agent-server", on_list_tools=list_tools, on_call_tool=call_tool)
```

`AgentMCPTool` uses the agent's name and description unless overridden.
`parameters` adds app-owned JSON Schema properties that remain available in the
raw MCP arguments. `chat_option_parameters` adds properties and explicitly
copies their values into Agent Framework chat options.

`call_tool(...)` validates the complete generated input schema, including
nested constraints, before conversion, agent execution, or session-store
access. Invalid arguments raise `MCPError` with `INVALID_PARAMS`. Valid exposed
chat options still override the agent's defaults. The adapter's
`mcp_to_run(...)` method remains a conversion helper, not a schema validator.

Treat `parameters` and `chat_option_parameters` as trusted application
configuration, not client-supplied schemas. Validation runs synchronously on
the server event loop and has no execution timeout. JSON Schema `pattern` and
`patternProperties` use Python's backtracking regular-expression engine.
Unsafe configured patterns can let caller-controlled values or property names
stall unrelated requests. Choose and test patterns with predictable matching
time for untrusted inputs; request-size limits alone do not make a
backtracking pattern safe. Applications requiring a hard validation deadline
must use an execution boundary that can be terminated, such as a separate
process. An asyncio timeout or worker thread cannot interrupt a running
standard-library regex match.

For a workflow exposed as one MCP tool, use `WorkflowMCPTool`:

```python
workflow_tool = WorkflowMCPTool(
    WorkflowState(create_workflow, cache_target=False),
    name="run_workflow",
)
```

The start executor must declare exactly one input type. Dataclass, Pydantic, and
other object-shaped inputs become the MCP tool's top-level arguments. Primitive
inputs are wrapped in the configurable `argument_name` property. The adapter
validates MCP arguments against that derived type before calling
`workflow.run(...)`.

Workflow instances preserve execution state, so applications that need
independent calls should supply a `WorkflowState` factory with
`cache_target=False`, as above. Checkpoint restoration, human-in-the-loop
responses, and continuation identifiers remain application-owned contracts.
If a workflow requests external input, the adapter raises instead of returning
an empty successful tool result.

Pass an existing `AgentState` plus `session_id_parameter` to persist an
`AgentSession`:

```python
state = AgentState(agent)
agent_tool = AgentMCPTool(
    state,
    parameters={"session_id": {"type": "string", "minLength": 1}},
    required_parameters={"session_id"},
    session_id_parameter="session_id",
)
```

The application must authenticate or authorize that session identifier and
serialize concurrent calls for the same session. The adapter only performs the
`AgentState` session-store get/run/set sequence. A configured session parameter
is always marked required in the generated MCP schema.

The session identifier is an opaque, application-defined key. Neither MCP nor
Agent Framework prescribes its format. `AgentMCPTool` treats it as the key for
one mutable conversation: each call loads that session and stores the updated
session under the same key. It does not implement
`previous_response_id`-style branching. Branching requires an app-owned
contract with separate source and destination identifiers so the application
can authorize both, copy the source session, and store the result under the
destination key.

MCP `tools/call` inputs are JSON objects defined by the app's `inputSchema`;
the protocol does not define image, audio, or resource content blocks for tool
arguments. This helper therefore converts one selected string argument and
does not impose a non-standard multimodal JSON convention.

For non-image/audio binary output, `mcp_from_run(...)` uses an app-provided
`content.additional_properties["uri"]` when present and otherwise uses the
short fallback `af://binary`; the payload itself is stored only in the MCP
resource's `blob` field.

`mcp_from_run(...)` targets `CallToolResult.content`, whose MCP content union
does not include sampling-only `ToolUseContent`. Agent Framework
`function_call` content is therefore omitted from tool results. MCP sampling
callbacks use a separate response contract and may convert function calls to
`ToolUseContent`.

MCP tool calls return one final `CallToolResult`; they do not stream partial
content blocks. Streamable HTTP may carry multiple MCP messages, and apps may
send progress notifications while work runs, but neither mechanism turns
Agent Framework response updates into incremental tool results. Experimental
MCP tasks defer retrieval of the same final result.

```python
run = mcp_to_run(arguments)
result = await agent.run(
    run["messages"],
    options=run["options"],
)
content = mcp_from_run(result)

# Native MCP SDK application code returns `content` from its call_tool handler.
```

The surrounding MCP application still owns the low-level `Server`, handler
registration, Starlette/FastAPI composition, stdio or streamable HTTP
transport, request authentication, session-key trust, concurrency, and
deployment.
