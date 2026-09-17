# agent-framework-hosting-a2a

Helpers for composing Agent Framework agents and workflows with an
application-owned native A2A server.

The package converts protocol values and can generate the common discovery
fields for a native `AgentCard`. It does not provide an `AgentExecutor`, task
lifecycle, event queue, task store, routes, session policy, authentication, or
deployment.

## Choose the level of help

| API | Adds |
| --- | --- |
| `a2a_to_run`, `a2a_from_run` | Native A2A-to-agent value conversion |
| `AgentA2AAdapter` | Agent card generation plus the agent conversion helpers |
| `a2a_to_workflow_run`, `a2a_from_workflow_run` | Typed workflow input and output conversion |
| `WorkflowA2AAdapter` | Workflow card generation plus the workflow conversion helpers |

Each level is optional. Applications keep using native A2A SDK objects and can
construct an `AgentCard` directly when they need discovery fields beyond the
common generated surface.

## Agent conversions

The core helpers work with any native A2A `AgentExecutor`:

```python
run = a2a_to_run(context.message, stream=False)
session_id = f"a2a:{context.tenant}:{context.context_id}"
session = await state.get_or_create_session(session_id)
result = await agent.run(
    run["messages"],
    session=session,
    options=run["options"],
    stream=run["stream"],
)
await state.set_session(session_id, session)
parts = a2a_from_run(result)

# Native A2A SDK application code publishes `parts` with TaskUpdater.
```

`a2a_from_run(...)` returns a flat part list and preserves content-level
metadata. The application decides how to group those parts into A2A messages
or artifacts and owns their message-level metadata and boundaries.

Standalone conversions are permissive by default. Pass `input_modes` or
`output_modes` to validate the converted parts against an advertised contract:

```python
run = a2a_to_run(message, input_modes=["text", "image/*"])
parts = a2a_from_run(result, output_modes=["text"])
```

### Mode parsing

A2A mode strings are extensible; there is no exhaustive protocol-wide list.
The helpers have an exhaustive set of built-in parsing behaviors:

| Mode | Automatic behavior |
| --- | --- |
| `text` | Uses A2A text parts and Agent Framework text content |
| `application/json` | Parses JSON text into an A2A data part and parses A2A data into typed workflow input |
| `application/octet-stream` | Uses raw byte parts |
| Concrete media types such as `image/png` or `audio/wav` | Preserves matching raw or URL parts |
| Wildcards such as `image/*` | Validates matching concrete media types |

Custom mode strings may still be advertised. They pass validation when the
native part already carries that exact media type, but conversion raises when
it would need to synthesize that representation without a built-in parser.
Configured mode values must be non-empty strings.

## Supported interfaces

`supported_interfaces` tells an A2A client where and how it can call the
application. Add one `AgentInterface` for each protocol binding the server
actually exposes:

```python
supported_interfaces = [
    AgentInterface(
        url="https://example.com/a2a",
        protocol_binding="JSONRPC",
    )
]
```

The `url` is the public base URL where the matching A2A routes are mounted;
include a path such as `/a2a` when the application mounts them below the
domain root. `protocol_binding` identifies the wire protocol implemented at
that URL, commonly `JSONRPC`, `HTTP+JSON`, or `GRPC`. Advertise only bindings
that the application has configured. `protocol_version` and `tenant` are
optional native A2A interface fields for deployments that use them.

## Generate an agent card

`AgentA2AAdapter` infers the public name and description from the agent and uses
conservative text input/output modes. Pass either an agent or an existing
`AgentState`; `get_card()` is async so factory-backed states can resolve their
target.

By default, the card also discovers Agent Framework `Skill` values from
`SkillsProvider` instances on the agent. The guaranteed skill frontmatter
name and description become a native A2A `AgentSkill`, using the card's input
and output modes. Set `infer_skills=False` to disable discovery. The `skills`
parameter also accepts explicit Agent Framework `Skill` values or fully
specified native A2A `AgentSkill` values when tags, examples, security, or
skill-specific modes need to be controlled directly. Card discovery happens
outside an agent run, so context-aware skill sources receive no session; use
explicit skills or disable inference when the advertised list is
session-specific.

Server capabilities stay explicit because they describe the public
application contract, not the agent's `run` method.

The adapter re-exposes `a2a_to_run(...)` and `a2a_from_run(...)`, so a native
executor can use the same object for card setup and request conversion without
importing the standalone helpers. Adapter conversions validate against the
configured card modes by default; pass `validate_modes=False` to opt out:

```python
run = adapter.a2a_to_run(context.message, stream=True)
parts = adapter.a2a_from_run(result)
```

```python
from a2a.types import AgentCapabilities, AgentInterface
from agent_framework_hosting_a2a import AgentA2AAdapter

card = await AgentA2AAdapter(
    state,
    version="1.0.0",
    supported_interfaces=[
        AgentInterface(url="https://example.com/a2a", protocol_binding="JSONRPC")
    ],
    capabilities=AgentCapabilities(streaming=True),
).get_card()
```

## Host a workflow

Workflow input conversion follows the single start-executor input type:

- strings use one A2A text part;
- bytes use one raw part;
- structured and scalar JSON values use one data part.

The output helper converts public workflow outputs to native A2A parts.
Pending human-input requests raise so the application can implement its own
continuation policy.

```python
workflow_input = a2a_to_workflow_run(context.message, workflow)
result = await workflow.run(workflow_input, stream=False)
parts = a2a_from_workflow_run(result)
```

`WorkflowA2AAdapter` infers modes from the workflow's declared input and output
types. It accepts a workflow or `WorkflowState`. Supply explicit modes for an
application-specific representation:

```python
card = await WorkflowA2AAdapter(
    workflow_state,
    version="1.0.0",
    supported_interfaces=[
        AgentInterface(url="https://example.com/a2a", protocol_binding="JSONRPC")
    ],
    skills=[workflow_skill],
).get_card()
```

It also exposes `await adapter.a2a_to_run(message)` and
`adapter.a2a_from_run(result)` for workflow conversion. These methods validate
against the effective card modes by default. When workflow output modes are
inferred, call `get_card()` before converting output so the adapter has
resolved the advertised contract.

Streaming workflow progress, artifacts, task status, checkpoints, and
human-in-the-loop continuation remain part of the native executor and
application contract.

The surrounding application may use Starlette, FastAPI, another ASGI
framework, or the A2A SDK's application builders.
