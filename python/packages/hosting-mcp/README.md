# agent-framework-hosting-mcp

MCP conversion helpers for app-owned Agent Framework hosting.

The package deliberately does not choose a web framework or wrap the MCP SDK
server lifecycle. It provides two conversion functions and small adapters:

- `mcp_to_run(...)` converts native MCP tool arguments into Agent Framework run
  arguments.
- `mcp_from_run(...)` converts an `AgentResponse` or `Message` into native MCP
  `ContentBlock` values.
- `MCPAgentTool(...)` generates the native `Tool` definition from an agent and
  keeps listing, parsing, execution, result conversion, and optional
  `AgentState` session persistence aligned.
- `MCPWorkflowTool(...)` generates the native `Tool` definition from a
  workflow's start-executor input type and converts completed workflow outputs.

Application code keeps ownership of the MCP SDK's `Server`, handler
registration, request context, transport, session-key policy, authentication,
authorization, and deployment.

For direct conversion, the argument name is part of the app-owned MCP tool
contract. Define it once and use the same value in both the native tool schema
and `mcp_to_run(...)`:

```python
agent_input_argument = "task"
chat_option_arguments = {
    "reasoning_effort": {
        "type": "string",
        "enum": ["low", "medium", "high"],
    },
}

tool = Tool(
    name="run_agent",
    inputSchema={
        "type": "object",
        "properties": {
            agent_input_argument: {"type": "string"},
            **chat_option_arguments,
        },
        "required": [agent_input_argument],
    },
)
run = mcp_to_run(
    arguments,
    argument_name=agent_input_argument,
    chat_option_arguments=chat_option_arguments,
)
```

Only names listed in `chat_option_arguments` are copied to `run["options"]`;
other MCP arguments remain available in the message's raw representation but
are not forwarded to the model client. The native MCP schema remains
responsible for validating exposed option types and ranges.

For an agent exposed as one MCP tool, use the adapter so the schema and
conversion cannot drift:

```python
agent_tool = MCPAgentTool(
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

@server.list_tools()
async def list_tools():
    return await agent_tool.list_tools()

@server.call_tool()
async def call_tool(name, arguments):
    return await agent_tool.call_tool(name, arguments)
```

`MCPAgentTool` uses the agent's name and description unless overridden.
`parameters` adds app-owned JSON Schema properties that remain available in the
raw MCP arguments. `chat_option_parameters` adds properties and explicitly
copies their values into Agent Framework chat options.

For a workflow exposed as one MCP tool, use `MCPWorkflowTool`:

```python
workflow_tool = MCPWorkflowTool(
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
agent_tool = MCPAgentTool(
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
Agent Framework prescribes its format. `MCPAgentTool` treats it as the key for
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
