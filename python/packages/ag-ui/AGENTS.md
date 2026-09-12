# AG-UI Package (agent-framework-ag-ui)

AG-UI protocol integration for building agent UIs with the AG-UI standard.

## Main Classes

- **`AgentFrameworkAgent`** - Wraps agents for AG-UI compatibility
- **`AgentFrameworkWorkflow`** - Wraps native `Workflow` objects, or accepts `workflow_factory(thread_id)` for thread-scoped workflow instances without subclassing
- **`AGUIChatClient`** - Chat client that speaks AG-UI protocol
- **`AGUIHttpService`** - HTTP service for AG-UI endpoints
- **`agent_framework_messages_to_agui_host_history()`** - Converts persisted Agent Framework messages to bounded
  AG-UI Host history while retaining MCP widget payloads and model replay metadata
- **`AGUIEventConverter`** - Converts between Agent Framework and AG-UI events
- **`add_agent_framework_fastapi_endpoint()`** - Add AG-UI endpoint to FastAPI app (`SupportsAgentRun` or `Workflow`)
- **`InMemoryAGUIThreadSnapshotStore`** - Memory-only latest AG-UI Thread Snapshot store for local development, demos, and tests

## Types

- **`AGUIRequest`** / **`AGUIChatOptions`** - Request types
- **`AGUIThreadSnapshot`** / **`AGUIThreadSnapshotStore`** - Thread snapshot model with client-replayable data,
  private Session Continuation State, and a scoped async store protocol
- **`availableInterrupts` / `resume`** - Optional canonical AG-UI `Interrupt` and `ResumeEntry` protocol data
- **`AgentState`** / **`RunMetadata`** - State management types
- **`PredictStateConfig`** - Configuration for state prediction

## Protocol Notes

- Outbound custom events are emitted as AG-UI `CUSTOM`.
- Usage metadata from `Content(type="usage")` is surfaced as `CUSTOM` events with `name="usage"`.
- Inbound custom event aliases are accepted: `CUSTOM`, `CUSTOM_EVENT`, and `custom_event`.
- Multimodal user inputs support both legacy (`text`, `binary`) and draft-style (`image`, `audio`, `video`, `document`) shapes.
- Interrupted runs complete with `RUN_FINISHED.outcome.type == "interrupt"` and canonical `outcome.interrupts`; do not document or add new flows that depend on the legacy top-level `RUN_FINISHED.interrupt` field.
- `Interrupt` and `ResumeEntry` come from the `ag-ui-protocol` package (`ag_ui.core`), not from an Agent Framework-specific interrupt model.
- Tool approval interrupts, including approvals surfaced through workflow `request_info`, advertise standard
  `approved` and full-replacement `editedArgs` responses while retaining the existing `accepted` alias and direct
  partial edits for MAF client compatibility. A `cancelled` resume completes normally without executing that call;
  resolved siblings in the same complete resume still proceed.
- Approval-time execution preserves each call's complete result group. Follow-up user-input requests remain in the
  resumed messages, while `TOOL_CALL_RESULT` events are emitted only for terminal `function_result` contents.
- Approval consent does not bypass policy. Built-in Agents receive validated local approvals through their normal
  `Agent.run` path, including Agent middleware, provider `before_run` preparation, and function middleware.
  `_approval_execution.py` tracks execution through existing function/chat middleware interfaces; it does not
  prepare providers or invoke the tools itself. `MiddlewareFailure` remains fatal.
- Queued approvals follow the wrapped Agent's scheduling. With `ToolApprovalMiddleware`, collected decisions
  remain pending until that middleware releases the batch; AG-UI does not execute a tool ahead of it.
  Collected server-side grants do not require the client to submit the same approval again.
- A2UI continuation retains the inner response's original model-turn and reasoning/call/result groups. UI
  rendering and its accounting remain adapter-owned while server tools use the existing function loop.
  Streaming uses an executable adapter handoff tool that returns a private control request through the existing
  function-result contract. That request is not a client approval prompt; completing the render clears only its
  matching internal pending request. A run-scoped control observer is installed once through the client's
  function-middleware extension point; its A2UI state is scoped to active stream pulls, preserving other runs'
  control outcomes and the original middleware's relative order.
  Adapter-side compatibility execution is limited to non-core agents without context providers; unsupported
  provider preparation fails explicitly instead of executing with a partial policy.
- Local approval resume checks the current function-invocation configuration before any approved side effect begins.
  When invocation is disabled, grants remain pending under their original retention deadline and the endpoint emits
  `APPROVAL_INVOCATION_DISABLED`; only a later explicit retry after re-enablement can execute them. Rejections and
  cancellations in a mixed resume still settle and retire their snapshot controls while grants remain pending.
  Repeating that mixed response or explicitly retrying it after re-enablement reuses retained terminal outcomes
  without reviving cancelled/rejected authority or replaying completed tool effects.
  Returning early or failing provider preparation releases every unstarted claimed grant, including hosted and
  deferred siblings, without extending pending retention or changing the execution owner. The adapter's in-run
  middleware rechecks enablement after provider preparation, before beginning any execution.
- Approval claim cleanup covers the complete run, including approval-time failures before streaming starts.
  In-run owners begin execution when the function or hosted request reaches its middleware seam. Cleanup releases
  unstarted claims without renewing retention and recovers possibly started executions without replaying
  uncertain work; settled and cancelled outcomes stay inert.
- Complete resume payloads may include a retained result alongside a distinct pending occurrence that reuses
  the provider call id. Match logical function-call occurrences and current request generations, not provider
  ids alone; an older request generation for the same occurrence is still invalid.
- Approval responses for tools injected during `before_run` are deferred to the in-run approval middleware rather
  than executed or rejected by the transport before those tools exist.
- `_approval_lifecycle.py` is the sole owner of approval occurrence registration, trusted aliases, authority
  validation, claims, terminal outcomes, and retry deduplication. Runner code normalizes AG-UI protocol values and
  projects lifecycle outcomes but must not maintain a parallel pending-approval registry.
- Local tool-approval interrupt ids use the Agent Framework `function_call.id` occurrence identity; `toolCallId`
  remains the provider/service `call_id`. Hosted approvals preserve the provider-issued approval request id. The
  lifecycle stores these identities separately so resume responses carry the authoritative approval occurrence id
  without rewriting tool-result correlation ids.
- Default stateless conversation history is client-controlled, including historical tool calls and results. Never
  document conversational tool results as authorization or policy evidence; use deterministic server-side checks,
  server-validated approvals, or scoped authoritative snapshots.
- AG-UI Thread and Run ids are client-owned protocol correlation ids. Service-session mode stores provider conversation
  or response ids privately in the thread snapshot. Set `service_session_id_from_thread_id=True` only for compatibility
  when the application intentionally uses a provider continuation id as its AG-UI Thread id.
- A configured Snapshot Scope and the client-owned Thread id are combined into a deterministic internal
  `AgentSession.session_id`. Keep the raw Thread id for protocol events and snapshot addressing so equal Thread ids
  in different trusted scopes cannot collide in context-provider state. The deprecated
  `legacy_session_id_from_thread_id=True` compatibility option preserves raw provider keys only for explicit
  migrations and must warn because it disables that isolation; it is unsafe for shared multi-tenant deployments.
  A configured endpoint resolver must return a non-empty string. Reject invalid results before accessing state or
  invoking the runner; absence of a resolver, not an invalid result, selects intentionally unscoped operation.
- `confirm_changes` snapshot cleanup resolves the synthetic confirmation back to its original `function_call_id`;
  it must never concatenate unrelated tool results or record accepted changes without a matching real result.
- SSE keepalive is endpoint-owned transport behavior configured through
  `add_agent_framework_fastapi_endpoint(keepalive_seconds=...)`. It emits SSE comments only; do not add `PING`,
  `HEARTBEAT`, or `KEEPALIVE` AG-UI events, and do not add runner-level keepalive settings.

## Usage

```python
from agent_framework.ag_ui import add_agent_framework_fastapi_endpoint
from fastapi import FastAPI

app = FastAPI()
add_agent_framework_fastapi_endpoint(app, agent)
```

## Import Path

```python
from agent_framework.ag_ui import AGUIChatClient, add_agent_framework_fastapi_endpoint

# or directly:
from agent_framework_ag_ui import AGUIChatClient
```
