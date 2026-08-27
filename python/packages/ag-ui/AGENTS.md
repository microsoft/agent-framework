# AG-UI Package (agent-framework-ag-ui)

AG-UI protocol integration for building agent UIs with the AG-UI standard.

## Main Classes

- **`AgentFrameworkAgent`** - Wraps agents for AG-UI compatibility
- **`AgentFrameworkWorkflow`** - Wraps native `Workflow` objects, or accepts `workflow_factory(thread_id)` for thread-scoped workflow instances without subclassing
- **`AGUIChatClient`** - Chat client that speaks AG-UI protocol
- **`AGUIHttpService`** - HTTP service for AG-UI endpoints
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
- Approval responses for tools injected during `before_run` are deferred to the in-run approval middleware rather
  than executed or rejected by the transport before those tools exist.
- `_approval_lifecycle.py` is the sole owner of approval occurrence registration, trusted aliases, authority
  validation, claims, terminal outcomes, and retry deduplication. Runner code normalizes AG-UI protocol values and
  projects lifecycle outcomes but must not maintain a parallel pending-approval registry.
- Default stateless conversation history is client-controlled, including historical tool calls and results. Never
  document conversational tool results as authorization or policy evidence; use deterministic server-side checks,
  server-validated approvals, or scoped authoritative snapshots.
- AG-UI Thread and Run ids are client-owned protocol correlation ids. Service-session mode stores provider conversation
  or response ids privately in the thread snapshot. Set `service_session_id_from_thread_id=True` only for compatibility
  when the application intentionally uses a provider continuation id as its AG-UI Thread id.
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
