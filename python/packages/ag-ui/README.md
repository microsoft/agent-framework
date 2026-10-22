# Agent Framework AG-UI Integration

AG-UI protocol integration for Agent Framework, enabling seamless integration with AG-UI's web interface and streaming protocol.

## Installation

```bash
pip install agent-framework-ag-ui
```

The base package supports Python 3.10–3.15. The optional A2UI integration
currently supports Python 3.10–3.14 because `ag-ui-a2ui-toolkit` declares
`Requires-Python <3.15`:

```bash
pip install "agent-framework-ag-ui[a2ui]"
```

## Quick Start

### Server (Host an AI Agent)

```python
from fastapi import FastAPI
from agent_framework import Agent
from agent_framework.openai import OpenAIChatCompletionClient
from agent_framework.ag_ui import add_agent_framework_fastapi_endpoint

# Create your agent
agent = Agent(
    name="my_agent",
    instructions="You are a helpful assistant.",
    client=OpenAIChatCompletionClient(
        azure_endpoint="https://your-resource.openai.azure.com/",
        model="gpt-4o-mini",
        api_key="your-api-key",
    ),
)

# Create FastAPI app and add AG-UI endpoint
app = FastAPI()
# Local/single-user only. Shared services must provide authorization_scope_resolver.
add_agent_framework_fastapi_endpoint(app, agent, "/", single_user=True)

# Run with: uvicorn main:app --reload
```

### Server (Host a Workflow)

```python
from fastapi import FastAPI
from agent_framework import WorkflowBuilder, WorkflowContext, executor
from agent_framework.ag_ui import add_agent_framework_fastapi_endpoint


@executor(id="start")
async def start(message: str, ctx: WorkflowContext) -> None:
    await ctx.yield_output(f"Workflow received: {message}")


workflow = WorkflowBuilder(start_executor=start).build()

app = FastAPI()
# Local/single-user only. Shared services must provide authorization_scope_resolver.
add_agent_framework_fastapi_endpoint(app, workflow, "/", single_user=True)
```

### Server (Thread-Scoped WorkflowBuilder)

Use `workflow_factory` when your workflow keeps runtime state (for example pending `request_info` interrupts) and must be isolated per AG-UI thread:

```python
from fastapi import FastAPI
from agent_framework import Workflow, WorkflowBuilder
from agent_framework.ag_ui import AgentFrameworkWorkflow, add_agent_framework_fastapi_endpoint


def build_workflow_for_thread(thread_id: str) -> Workflow:
    # Build a fresh workflow instance for each thread id.
    return WorkflowBuilder(start_executor=...).build()


app = FastAPI()
thread_scoped_workflow = AgentFrameworkWorkflow(
    workflow_factory=build_workflow_for_thread,
    name="my_workflow",
)
# Local/single-user only. Shared services must provide authorization_scope_resolver.
add_agent_framework_fastapi_endpoint(app, thread_scoped_workflow, "/", single_user=True)
```

### Client (Connect to an AG-UI Server)

```python
import asyncio
from agent_framework.ag_ui import AGUIChatClient


async def main():
    async with AGUIChatClient(endpoint="http://localhost:8000/") as client:
        # Stream responses
        async for update in client.get_response("Hello!", stream=True):
            for content in update.contents:
                if content.type == "text" and content.text:
                    print(content.text, end="", flush=True)
        print()


asyncio.run(main())
```

The `AGUIChatClient` supports:
- Streaming and non-streaming responses
- Hybrid tool execution (client-side + server-side tools)
- Automatic thread management for conversation continuity
- Integration with `Agent` for client-side history management
- Canonical interrupt/resume passthrough (`availableInterrupts` and `resume`)

#### HTTP client ownership and cookies

**Breaking change:** `AGUIChatClient` and `AGUIHttpService` reuse an internally owned HTTP client
for connection pooling but no longer persist response cookies. This applies to all runs,
including repeated requests with the same thread ID. Closing the AG-UI client or leaving
its async context manager closes its internally owned HTTP client.

Applications that need cookies for upstream authentication, sessions, or load-balancer affinity, including those migrating from
the previous default of retaining response cookies, must supply an `httpx.AsyncClient`
through `http_client`. Supplied clients retain their headers, cookies, timeout, transport,
and response-cookie handling, and must be closed by the caller. Scope a cookie-bearing
client to a single authenticated principal; do not share it across users. AG-UI thread IDs
are correlation identifiers, not authentication boundaries.

## Citations and annotations

Text content carrying `Content.annotations` emits a message-linked `CUSTOM` event named `annotations`.
This includes annotation-only updates received after the response text, such as SharePoint grounding
citations from the Responses API. The event arrives before `RUN_FINISHED` and does not repeat response text:

```json
{
  "type": "CUSTOM",
  "name": "annotations",
  "value": {
    "messageId": "assistant-message-id",
    "annotations": [
      {
        "type": "citation",
        "title": "Document",
        "url": "https://example.sharepoint.com/document.pdf",
        "annotated_regions": [
          {"type": "text_span", "start_index": 0, "end_index": 6}
        ]
      }
    ]
  }
}
```

Each event contains a batch of newly emitted annotations for the indicated text message. Frontends can
append those annotations to that message and use the citation URL, title, or file ID to render sources.
Framework annotation fields and additional properties are retained, but provider `raw_representation`
objects are omitted.

`AGUIChatClient` restores these batches as `Content.annotations` in streaming updates and aggregated
responses, while retaining the custom-event payload in `update.additional_properties["ag_ui_custom_event"]`.
Custom events are live run metadata: citation rendering and persistence alongside frontend message history
remain application responsibilities; `MESSAGES_SNAPSHOT` does not restore these custom events.

## Tool Return Helpers

Use `state_update` when a backend tool needs to send different payloads to the model, the UI, and shared state. The `text` value remains the LLM-bound tool result, `tool_result` becomes the AG-UI `ToolCallResultEvent.content` for frontend rendering, and `state` is merged into durable shared state.

```python
from agent_framework import Content, tool
from agent_framework.ag_ui import state_update


@tool
async def get_weather(city: str) -> Content:
    data = await fetch_weather(city)
    return state_update(
        text=f"{city}: {data['temp']}°C and {data['conditions']}",
        tool_result={
            "component": "weather-card",
            "city": city,
            "temperature": data["temp"],
            "conditions": data["conditions"],
            "humidity": data["humidity"],
        },
        state={"weather": {"city": city, **data}},
    )
```

## Documentation

- **[Getting Started Tutorial](getting_started/)** - Step-by-step guide to building AG-UI servers and clients
  - Server setup with FastAPI
  - Client examples using `AGUIChatClient`
  - Hybrid tool execution (client-side + server-side)
  - Thread management and conversation continuity
- **[Examples](agent_framework_ag_ui_examples/)** - Complete examples for AG-UI features

## Interrupts and Resume

Agent Framework AG-UI uses the canonical AG-UI interrupt protocol. Paused agent approval and workflow
`request_info` runs finish with `RUN_FINISHED.outcome.type == "interrupt"` and a non-empty
`RUN_FINISHED.outcome.interrupts` array. Agent Framework does not define a separate interrupt model; use
`ag_ui.core.Interrupt` and `ag_ui.core.ResumeEntry` when constructing typed request data in Python.

Tool approval interrupts use `reason: "tool_call"` and include `toolCallId` when the pause is bound to a tool call.
Workflow `request_info` interrupts use `reason: "input_required"`. Framework-specific details needed for resume
validation live in each interrupt's `metadata`, while generic clients can render the human-readable `message` and
`responseSchema`.

Interrupted terminal event shape:

```json
{
  "type": "RUN_FINISHED",
  "outcome": {
    "type": "interrupt",
    "interrupts": [
      {
        "id": "approval_1",
        "reason": "tool_call",
        "message": "Approve tool call get_weather?",
        "toolCallId": "tool_call_1",
        "responseSchema": {
          "type": "object",
          "properties": {
            "approved": { "type": "boolean" },
            "accepted": { "type": "boolean" },
            "city": { "type": "string" },
            "editedArgs": {
              "type": "object",
              "description": "Full replacement of the tool arguments. Not merged.",
              "properties": {
                "city": { "type": "string" }
              },
              "required": ["city"],
              "additionalProperties": false
            }
          },
          "anyOf": [
            { "required": ["approved"] },
            { "required": ["accepted"] }
          ]
        },
        "metadata": {
          "agent_framework": {
            "type": "function_approval_request",
            "function_call": {
              "call_id": "tool_call_1",
              "name": "get_weather",
              "arguments": {
                "city": "Seattle"
              }
            }
          }
        }
      }
    ]
  }
}
```

Resume the paused thread with a canonical `resume` array. Each entry addresses exactly one open interrupt by
`interruptId`; `status` is `resolved` or `cancelled`; resolved entries carry the approval or workflow response payload.
Tool approvals use the standard `approved` field and may provide `editedArgs` as a full replacement of the tool
arguments. For compatibility with existing MAF clients, `accepted` remains an alias for `approved`, and direct
argument fields remain supported as partial edits. Cancellation is a normal terminal decision: cancelled calls do
not execute, while resolved siblings in the same complete resume continue normally. The same tool-approval shape and
resume payloads apply when an agent approval is surfaced through a workflow `request_info` event.

For built-in Agents, validated approvals resume through the normal `Agent.run()` path. Agent middleware still
controls admission and scheduling, and provider and function middleware still apply before tool execution.
For example, `ToolApprovalMiddleware` collects queued decisions before releasing the batch; AG-UI does not
execute an individually approved tool ahead of that middleware. Completed results remain replayable without
repeating tool execution.

```json
{
  "threadId": "thread-1",
  "messages": [],
  "resume": [
    {
      "interruptId": "approval_1",
      "status": "resolved",
      "payload": {
        "approved": true
      }
    }
  ]
}
```

This is a clean release-candidate breaking change before `1.0.0`: new interrupted runs use
`RUN_FINISHED.outcome.interrupts` and do not emit a stable top-level `RUN_FINISHED.interrupt` field. Normal
non-interrupted runs continue to finish with valid `RUN_FINISHED` terminal events.

## Public API Review Notes

The Python package is currently in release candidate stage and is targeting the released `1.0.0` API surface. The preferred application import path is `agent_framework.ag_ui`; direct package imports from `agent_framework_ag_ui` are also supported.

Review focus: whether these names are the right stable contract for Python users, and whether the protocol interrupt fields below match AG-UI's expected pause/resume shape.

| Surface | Public exports |
| --- | --- |
| `agent_framework.ag_ui` facade | `AgentFrameworkAgent`, `AgentFrameworkWorkflow`, `AGUIChatClient`, `AGUIEventConverter`, `AGUIHttpService`, `AGUIThreadSnapshot`, `AGUIThreadSnapshotStore`, `AuthorizationScopeResolver`, `InMemoryAGUIThreadSnapshotStore`, `SnapshotScopeResolver`, `add_agent_framework_fastapi_endpoint`, `state_carrier`, `state_update`, `__version__` |
| Direct `agent_framework_ag_ui` package | Facade exports plus `AGUIChatOptions`, `AGUIRequest`, `AGUIThreadID`, `AgentState`, `DEFAULT_MAX_THREAD_SNAPSHOTS`, `DEFAULT_TAGS`, `PredictStateConfig`, `RunMetadata`, `SnapshotScope`, `WorkflowFactory` |
| AG-UI protocol package (`ag_ui.core`) | `Interrupt`, `ResumeEntry`, `RunFinishedInterruptOutcome`, and related run outcome models |

Interrupt support is protocol data rather than a separate Agent Framework Python class. Requests accept canonical `availableInterrupts`/`available_interrupts` and `resume` values; `AGUIChatClient` and `AGUIHttpService.post_run(...)` forward those fields with AG-UI wire aliases; agent approval and workflow `request_info` pauses emit `RUN_FINISHED.outcome.interrupts`; `AGUIEventConverter` preserves canonical interrupt outcome metadata on the final `ChatResponseUpdate`; and thread snapshot hydration replays the canonical interrupt outcome when a scoped snapshot stores an unresolved pause.

Use `state_carrier(...)` to mark JSON content that should be sent in the AG-UI request's `state` field rather than as a model-visible document. The client removes explicitly marked carriers from all client-controlled history and uses the most recent carrier. Ordinary `application/json` content remains a document. For migration, pass `allow_legacy_state_carrier=True` in `AGUIChatOptions` to recognize the deprecated final single-content base64 JSON convention; mixed text and document messages remain model-visible. This client-only option emits a `DeprecationWarning` when the legacy convention is used and is not sent to the remote server.

## Features

This integration supports all 7 AG-UI features:

1. **Agentic Chat**: Basic streaming chat with tool calling support
2. **Backend Tool Rendering**: Tools executed on backend with results streamed to client
3. **Human in the Loop**: Function approval requests for user confirmation before tool execution
4. **Agentic Generative UI**: Async tools for long-running operations with progress updates
5. **Tool-based Generative UI**: Custom UI components rendered on frontend based on tool calls
6. **Shared State**: Bidirectional state sync between client and server
7. **Predictive State Updates**: Stream tool arguments as optimistic state updates during execution

Additional compatibility and draft support:
- Native `Workflow` endpoint registration via `add_agent_framework_fastapi_endpoint(...)`
- Workflow-to-AG-UI event mapping (run/step/activity/tool/custom events)
- Custom event compatibility for inbound `CUSTOM`, `CUSTOM_EVENT`, and `custom_event`
- Pragmatic multimodal input parsing for both legacy (`binary`) and draft media-part shapes
- Canonical interrupt/resume handling (`availableInterrupts`, `resume`, and `RUN_FINISHED.outcome.interrupts`)

## Security: Authentication & Authorization

Every AG-UI endpoint must choose an authorization mode:

- **Authenticated/shared applications:** provide `authorization_scope_resolver`. FastAPI invokes it as a dependency, so
  it can declare `Depends`, `Security`, header, cookie, or `Request` parameters. It must return a stable, non-empty
  scope for the authenticated principal or collaboration boundary that may access the same server-side AG-UI state.
- **Local or genuinely single-user applications:** set `single_user=True`. This deliberately treats every caller as
  one authorization principal and assigns an opaque scope for the lifetime of that endpoint registration. Do not use
  it on a shared service or where durable state must retain the same scope across process restarts.
- **Compatibility:** existing `snapshot_scope_resolver` integrations remain supported and provide the same trusted
  scope to snapshots, internal sessions, workflows, detached-run admission, and approvals.

Authentication in the separate `dependencies` list can allow or reject a request, but its return value does not scope
server-side state. Do not combine authentication-only dependencies with `single_user=True` when different authenticated
callers can reach the endpoint.

### Stable Single-User Scope

`single_user=True` creates an opaque scope for one endpoint registration, which is appropriate for local and
process-local examples. A single-user application that uses durable snapshots, checkpoints, or provider state can
instead provide an application-owned constant through the normal resolver:

```python
def resolve_single_user_scope() -> str:
    # Keep this stable for the lifetime of the persisted state and unique to this application boundary.
    return "my-app:single-user:v1"


add_agent_framework_fastapi_endpoint(
    app,
    agent,
    "/",
    authorization_scope_resolver=resolve_single_user_scope,
)
```

The value is a server-owned namespace, not a credential. Do not read it from AG-UI request state or other
client-controlled input.

### API Key Authentication Example

```python
import os
from fastapi import FastAPI, HTTPException, Security
from fastapi.security import APIKeyHeader
from agent_framework import Agent
from agent_framework.ag_ui import add_agent_framework_fastapi_endpoint

# Configure API key authentication
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
EXPECTED_API_KEY = os.environ.get("AG_UI_API_KEY")


async def resolve_authorization_scope(api_key: str | None = Security(API_KEY_HEADER)) -> str:
    """Verify the API key and return the state-ownership scope."""
    if not api_key or api_key != EXPECTED_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return "configured-api-key"


# Create agent and app
agent = Agent(name="my_agent", instructions="...", client=...)
app = FastAPI()

# Register endpoint with authentication-backed authorization scoping
add_agent_framework_fastapi_endpoint(
    app,
    agent,
    "/",
    authorization_scope_resolver=resolve_authorization_scope,
)
```

### Other Authentication Options

The authorization resolver is a normal FastAPI dependency, enabling integration with:

- **OAuth 2.0 / OpenID Connect** - Use `fastapi.security.OAuth2PasswordBearer`
- **JWT Tokens** - Validate tokens with libraries like `python-jose`
- **Azure AD / Entra ID** - Use `azure-identity` for Microsoft identity platform
- **Rate Limiting** - Add request throttling dependencies
- **Custom Authentication** - Implement your organization's auth requirements

For a complete authentication example, see [getting_started/server.py](getting_started/server.py).

### Conversation and Tool Result Trust

In the default stateless mode, the AG-UI client sends the conversation history for each run. Treat that history as
untrusted input, including client-supplied `assistant` tool calls and `tool` results. A historical tool result is not
proof that the server emitted the matching call or executed the named backend tool.

Do not use conversation history, tool results, or the model's decision to call a tool as an authorization,
entitlement, approval, or policy signal. Enforce security decisions deterministically in authenticated server code,
such as endpoint dependencies, tool middleware, or the server-validated human-in-the-loop approval flow. Tool
implementations must also authorize the current principal before accessing protected data or performing sensitive
actions.

For applications that need server-authoritative thread history, configure scoped AG-UI Thread Snapshots. Snapshot
mode only accepts user turns and results for backend-issued tool calls when extending stored history. It complements
endpoint authentication and authorization; it does not replace them.

## AG-UI Thread Snapshots

AG-UI Thread Snapshot persistence is opt-in and disabled by default. Existing endpoints keep their current behavior
unless you provide a `snapshot_store`.

Thread snapshots let an AG-UI frontend recover replayable UI state after a refresh. When snapshot persistence is
enabled, the endpoint stores the latest replayable snapshot for an AG-UI Thread within an application-defined
Snapshot Scope. A Hydrate Request is an AG-UI request with a known `threadId`, `messages: []`, and no `resume`
payload. Hydration replays the stored Shared State, message snapshot, and canonical interrupt outcome when available,
then finishes without invoking the wrapped agent or workflow.

Use the built-in in-memory store for local development, demos, and tests:

```python
from fastapi import FastAPI

from agent_framework.ag_ui import InMemoryAGUIThreadSnapshotStore, add_agent_framework_fastapi_endpoint

app = FastAPI()
agent = ...
snapshot_store = InMemoryAGUIThreadSnapshotStore(max_snapshots=500)


add_agent_framework_fastapi_endpoint(
    app,
    agent,
    "/",
    snapshot_store=snapshot_store,
    single_user=True,
)
```

For a shared deployment, replace `single_user=True` with the authenticated
`authorization_scope_resolver` shown above.

Configured stateless agent snapshot stores are updated after function/MCP tool-result batches and approval safe points,
then written once more with the terminal run state. These boundaries capture completed model/tool rounds without
persisting sibling text or reasoning whose stream finalizer may still reject it. Intermediate snapshots project only
completed call/result groups and current approval controls; the terminal snapshot retains the complete finalized
output. Service-session snapshots retain terminal-save cadence so replayable messages cannot advance without their
matching provider continuation state. Workflow Thread Snapshots also keep their terminal-save cadence; workflow
checkpointing remains the mechanism for incremental workflow runtime state.

A frontend can then hydrate the latest stored snapshot for the scoped thread:

```json
{
  "threadId": "thread-1",
  "messages": []
}
```

### Disconnect-safe runs

By default, AG-UI execution remains attached to the SSE response: disconnecting the client cancels the response
generator and can stop the run. Set `detached_runs=True` when a finite agent or workflow run must continue through
snapshot, checkpoint, and approval-state finalization after the HTTP reader disconnects:

```python
add_agent_framework_fastapi_endpoint(
    app,
    agent,
    "/",
    snapshot_store=snapshot_store,
    single_user=True,
    detached_runs=True,
    max_detached_runs=32,
    detached_run_timeout_seconds=3600,
)
```

Detached execution uses a bounded endpoint-owned producer queue. While a detached mutating request is active, another
mutating request for the same `(Snapshot Scope, threadId)` returns HTTP 409; an empty snapshot Hydrate Request remains
allowed, bypasses detached producer capacity, and returns the latest committed safe point. Equal Thread ids in
different Snapshot Scopes remain independent.
Each endpoint registration retains at most `max_detached_runs` producers (32 by default); requests beyond that limit
receive HTTP 503. After a reader disconnects or never starts, `detached_run_timeout_seconds` cancels a stalled producer
and releases its capacity (one hour by default).

This option does not add resumable event replay. Events emitted while no client is attached are consumed and discarded,
so a reconnecting client recovers from Thread Snapshots rather than resuming the original SSE position. Applications
that require replay of every in-flight event must provide their own authenticated event log and resume route with
retention and cross-replica semantics appropriate to their deployment.

FastAPI dependencies and other request-scoped resources may be released after the disconnected response ends. Resolve
authorization, Snapshot Scope, and other durable values before the run starts; detached tools and providers must not
retain request-owned clients or sessions that are expected to close with the HTTP request.

Endpoint registration requires `authorization_scope_resolver`, the compatible `snapshot_scope_resolver`, or an
explicit `single_user=True` declaration. The authenticated resolver returns the application-defined scope used with
the AG-UI Thread id for snapshot storage, internal `AgentSession.session_id` derivation, workflow ownership,
detached-run admission, and approval state. Context providers and workflow instances therefore cannot merge
server-side state for equal Thread ids in different scopes. The raw Thread id remains unchanged in AG-UI events and
snapshot operations. `single_user=True` assigns one opaque scope per endpoint registration, including endpoints that
share the same route path or backing objects in one process. That scope changes when the endpoint is registered again;
use an explicit resolver for durable snapshots, checkpoints, or provider state that must survive process restarts.

A workflow request that omits `threadId` is assigned a generated Thread id. It is reported in `RUN_STARTED`, keys the
`workflow_factory` instance and Thread Snapshot, and owns that run's pending `request_info` interrupts. Send it back as
`threadId` to continue the run; a continuation that omits it receives `WORKFLOW_RESUME_NOT_FOUND`. With
`workflow_factory`, a request without `threadId` that carries a `resume` entry, a tool result, or an approval response
is rejected the same way instead of starting a new run, so send `threadId` with every such request. A checkpoint
created by such a run resumes with `checkpointId` and either the reported `threadId` or, as before, no `threadId`.

Authenticate and authorize the current scope on every request, including hydration and approval resume, rather than
trusting a scope supplied through Shared State or forwarded properties. A configured resolver must return a non-empty
string. Returning `None`, an empty string, or another type fails the request with a generic HTTP 500 configuration
error before accessing snapshots, approval state, or context providers. Resolver failures never fall back to
single-user or unscoped operation. Valid scope strings are used exactly as returned, without trimming or normalization.
Use endpoint authentication dependencies to reject unauthorized requests before scope resolution.

Existing applications that need time to migrate provider records from raw Thread-id keys can temporarily wrap the
agent with `AgentFrameworkAgent(..., legacy_session_id_from_thread_id=True)`. This deprecated compatibility option
emits a `DeprecationWarning` and disables Snapshot Scope isolation for context-provider state. It is not safe for a
shared multi-tenant deployment, even with a trusted resolver. Keep it disabled when establishing scope isolation.

### Request state and snapshot authority

For hosted agents, request Shared State is also available through `AgentSession.state` during that run, whether or
not snapshot persistence is configured. Request values are untrusted per-run context: they overlay ordinary restored
values, are not passed through typed session restoration, and are excluded from private Session Continuation State.
Keys owned by configured context providers or reserved for approval, message-injection, and standalone FIDES security
middleware are not copied into `AgentSession.state`; their server-owned values take precedence over client Shared State.
A custom FIDES `session_state_key` is protected when its middleware is visible on the agent or its client before the
run; use `SecureAgentConfig` for middleware that a context provider injects later.

When scoped snapshots are configured, each category has one State Authority:

| State category | State Authority |
| --- | --- |
| Conversation history | AG-UI Thread Snapshot messages |
| AG-UI Shared State and request context | The current AG-UI request and replayable snapshot state |
| Approval State | The Approval State Store |
| Other server-produced provider working state | Private Session Continuation State |

Session Continuation State is stored atomically in the optional `AGUIThreadSnapshot.session_state` field and restored
through the core `AgentSession` typed serialization contract. It is never accepted from an AG-UI request or emitted
during hydration. Deleting a scoped thread snapshot resets its replayable and private state together, and clearing a
Snapshot Scope removes all such records in that scope. Missing or empty request Shared State is not a reset command.
If private continuation cannot be restored or serialized, the endpoint logs the failure and continues without that
continuation so stale or unsupported provider state cannot permanently block the thread or suppress `RUN_FINISHED`.

AG-UI Thread ids identify AG-UI Threads; they do not authorize snapshot access. Do not treat a thread id as a bearer
credential or tenant boundary. Production applications must authenticate and authorize every AG-UI endpoint request
and choose a Snapshot Scope that represents the app's real access boundary, such as an authenticated user, tenant,
or workspace. Do not rely on untrusted client-provided fields by themselves to choose that boundary.

Tool approval resumes are validated against server-owned Approval State. The default Approval State store is
process-local and bounded, and stores only approval-specific state needed to validate and continue pending approvals.
It is not an authentication, tenant authorization, or distributed durability mechanism; production applications remain
responsible for endpoint authentication, tenant authorization, and deployment/storage architecture that matches their
availability and worker topology requirements.

Snapshot storage is treated as trusted server-side storage because private continuation is eligible for typed core
restoration; applications are responsible for providing its integrity protection. Snapshots also have confidentiality
impact: they may contain sensitive user text, model output, tool results, function arguments, UI payloads, Shared State,
interrupt data, and private provider working state. The built-in `InMemoryAGUIThreadSnapshotStore` is in-memory only,
process-local, bounded, latest-only, and not durable production storage. It is cleared on process restart and is not
shared across workers.

No file-backed AG-UI snapshot store is provided by the package. Applications that need durable persistence should
provide an app-owned implementation of the `AGUIThreadSnapshotStore` protocol and own storage hardening, including
encryption, integrity protection, access control, retention, audit, data residency, and deletion behavior. Existing
custom stores remain source-compatible because `session_state` is optional, but they provide Session State Continuity
only when they round-trip that field unchanged with the rest of the snapshot.

The supported consistency model is one active run per `(Snapshot Scope, threadId)`. With `detached_runs=True`, one
registered endpoint enforces that rule in-process by rejecting concurrent mutations while allowing hydration.
Coordination is not shared across endpoint registrations, workers, or replicas; applications that require distributed
serialization must provide it using infrastructure appropriate to their deployment. Without detached execution,
concurrent writes to the same scoped thread remain last-writer-wins.

## Architecture

The package uses a clean, orchestrator-based architecture:

- **AgentFrameworkAgent**: Lightweight wrapper that delegates to orchestrators
- **Orchestrators**: Handle different execution flows (default, human-in-the-loop, etc.)
- **Confirmation Strategies**: Domain-specific confirmation messages (extensible)
- **AgentFrameworkEventBridge**: Converts Agent Framework events to AG-UI events
- **Message Adapters**: Bidirectional conversion between AG-UI and Agent Framework message formats
- **FastAPI Endpoint**: Streaming HTTP endpoint with Server-Sent Events (SSE)

## Next Steps

1. **New to AG-UI?** Start with the [Getting Started Tutorial](getting_started/)
2. **Want to see examples?** Check out the [Examples](agent_framework_ag_ui_examples/) for AG-UI features

## License

MIT
