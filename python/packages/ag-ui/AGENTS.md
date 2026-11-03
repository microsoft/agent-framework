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
- **`AuthorizationScopeResolver`** - FastAPI dependency callable that resolves authenticated endpoint ownership
- **`AGUIThreadSnapshot`** / **`AGUIThreadSnapshotStore`** - Thread snapshot model with client-replayable data,
  private Session Continuation State, and a scoped async store protocol
- **`availableInterrupts` / `resume`** - Optional canonical AG-UI `Interrupt` and `ResumeEntry` protocol data
- **`AgentState`** / **`RunMetadata`** - State management types
- **`PredictStateConfig`** - Configuration for state prediction

## Protocol Notes

- Outbound custom events are emitted as AG-UI `CUSTOM`. Content-free `AgentResponseUpdate` metadata does not
  produce a workflow-output event.
- Usage metadata from `Content(type="usage")` is surfaced as `CUSTOM` events with `name="usage"`.
- Text annotations are surfaced as `CUSTOM` events with `name="annotations"` and
  `value={"messageId": ..., "annotations": [...]}`. Annotation-only updates announce a text message if needed
  without emitting empty text deltas. Provider `raw_representation` is omitted; `AGUIChatClient` restores the
  annotations on text content. Content-coordinate regions on text deltas are rebased to accumulated-message
  offsets; source-coordinate regions are preserved unchanged. These live custom events are not replayed by
  `MESSAGES_SNAPSHOT`.
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
- Programmatic `AgentFrameworkAgent.run(...)` and `run_agent_stream(...)` calls accept
  `function_invocation_kwargs` and preserve that tool-runtime context across approval resume. Adapter-local execution
  merges only that mapping, the wrapped agent's default `additional_function_arguments`, and the current run options
  (in increasing precedence), not unrelated AG-UI run kwargs.
- Queued approvals follow the wrapped Agent's scheduling. With `ToolApprovalMiddleware`, collected decisions
  remain pending until that middleware releases the batch; AG-UI does not execute a tool ahead of it.
  Collected server-side grants do not require the client to submit the same approval again.
- `AGUIChatClient` follows the shared function-loop completion contract rather than requiring provider-specific
  finish markers. Complete arguments may execute without `TOOL_CALL_END`; when `RUN_ERROR` invalidates a response
  after a local client-tool call has been exposed, raise `ResponseInvalidatedException` so the function loop and
  direct stream consumers discard that call.
- A2UI continuation retains the inner response's original model-turn and reasoning/call/result groups. UI
  rendering and its accounting remain adapter-owned while server tools use the existing function loop.
  Streaming uses an executable adapter handoff tool that returns a private control request through the existing
  function-result contract. That request is not a client approval prompt; completing the render clears only its
  matching internal pending request. Rendering uses the completed handoff's effective arguments, keyed by
  function-call occurrence, rather than the original streamed model arguments. Only privately marked requests
  for the adapter's handoff tool are hidden. Unmarked requests remain visible; a pending approval for that tool
  suspends rendering in both native and opaque-agent modes.
  Session-backed approval flows let core retain implicit siblings without requesting extra user decisions;
  stateless flows preserve the approvals core surfaces. A run-scoped control observer is installed once through the
  client's function-middleware extension point; its A2UI state is scoped to active stream pulls, preserving other runs'
  control outcomes and the original middleware's relative order.
  Adapter-side compatibility execution is limited to non-core agents without context providers; unsupported
  provider preparation fails explicitly instead of executing with a partial policy.
  Client `forwardedProps.injectA2UITool` is only a per-request request to use a capability the backend has already
  enabled with `a2ui_config["inject_a2ui_tool"]`; request metadata alone must never activate a server tool or sub-agent.
  Resolve that backend opt-in before importing optional A2UI support so a client flag cannot make an otherwise
  non-A2UI deployment fail on a missing optional dependency.
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
- Hosted/local execution ownership comes from `function_call.hosted`; `server_name` supplies the hosted-server
  boundary persisted as `ApprovalOccurrence.server_label`. Legacy `additional_properties["server_label"]` remains a
  compatibility input, not the primary routing signal.
- Default stateless conversation history is client-controlled, including historical tool calls and results. Never
  document conversational tool results as authorization or policy evidence; use deterministic server-side checks,
  server-validated approvals, or scoped authoritative snapshots.
- AG-UI Thread and Run ids are client-owned protocol correlation ids. Service-session mode stores provider conversation
  or response ids privately in the thread snapshot. Set `service_session_id_from_thread_id=True` only for compatibility
  when the application intentionally uses a provider continuation id as its AG-UI Thread id.
- A workflow run resolves its Thread id once. A generated id for an omitted `threadId` is the id reported in
  `RUN_STARTED`, keys the `workflow_factory` cache and Thread Snapshot, and owns the run's live `request_info`
  interrupts, so a continuation must send it back. A `workflow_factory` request without `threadId` that carries a
  `resume` entry or a tool or approval-response message (as `_extract_responses_from_messages` defines them) is
  rejected with `WORKFLOW_RESUME_NOT_FOUND` before a workflow instance is built. Checkpoint ownership binds only
  client-supplied Thread ids; a checkpoint of a run without one also records the generated id as an alias, so both
  the reported id and legacy id-less restores resume it.
- A configured Snapshot Scope and the client-owned Thread id are combined into a deterministic internal
  `AgentSession.session_id`. Keep the raw Thread id for protocol events and snapshot addressing so equal Thread ids
  in different trusted scopes cannot collide in context-provider state. The deprecated
  `legacy_session_id_from_thread_id=True` compatibility option preserves raw provider keys only for explicit
  migrations and must warn because it disables that isolation; it is unsafe for shared multi-tenant deployments.
  Endpoint registration must explicitly provide `authorization_scope_resolver`, retain the compatible
  `snapshot_scope_resolver`, or declare `single_user=True`. The authorization resolver is a FastAPI dependency and
  must return a non-empty string derived from authenticated request context. Reject invalid results before accessing
  state or invoking the runner; never fall back to single-user or unscoped operation after a configured resolver fails.
  `single_user=True` assigns one opaque authorization scope for the lifetime of that endpoint registration and must not
  be used for callers with distinct authorization. Use an explicit resolver when snapshots, checkpoints, or provider
  state must retain the same scope across process restarts.
- Request `state` is client-owned Shared State and is merged into `AgentSession.state`, minus a protected set:
  tool-approval state, history/context-provider namespaces, message-injection state, standalone FIDES security
  state, and provider-owned keys.
  When state is exposed to the model, keep it in an explicitly untrusted user-data message; never promote request
  state values into system/developer instruction authority.
  Agents declare the latter through a `service_session_state_keys` attribute, but that resolves against the agent
  object AG-UI is handed, so a wrapper agent that does not forward it would silently drop the protection.
  `_RESERVED_SERVICE_SESSION_STATE_KEYS` therefore reserves such keys unconditionally; add a key there whenever
  it names a remote resource that the server's own credentialed call addresses.
- `ToolApprovalMiddleware` names its session state with an application-chosen `source_id`, which a wrapper can hide
  from the agent AG-UI is handed. Tool approval authority is therefore also protected by shape, not only by name: a
  client Shared State value holding a non-empty `rules`, `queued_approval_requests` or `collected_approval_responses`
  list is never merged into `AgentSession.state`, whatever its item encoding (`ToolApprovalState` loads more than
  JSON objects), and a key that already holds that state in restored server state, as a mapping or a
  `ToolApprovalState` object, cannot be replaced by client values. An ignored key stays in Shared State and the
  model context; it is only not mirrored into the session.
  Wrapper agents should still forward `middleware`, `context_providers` and `service_session_state_keys`, and
  `_TOOL_APPROVAL_STATE_FIELDS` must stay in sync with `ToolApprovalState`.
- Provider-owned keys identify remote resources that the server's own credentialed call addresses — for example
  the Foundry hosted-agent session ID, which selects a VM-isolated sandbox with a persistent filesystem. Never let
  request state choose one. `AgentSession.service_session_id` is deliberately a separate attribute rather than a
  `state` entry, so conversation continuation is unreachable from client input by construction; keep it that way.
- Standalone FIDES security middleware (`LabelTrackingFunctionMiddleware`, `PolicyEnforcementFunctionMiddleware`)
  keeps its context label, hidden variables, and pending policy approvals in `AgentSession.state` under
  `_FIDES_SESSION_STATE_KEY` or the `session_state_key` it was configured with. Request and stored Shared State must
  never supply that state. The default key is always protected; a configured key is discovered from middleware visible
  on the agent or its client before the run, so middleware injected later or hidden behind a wrapper that does not
  expose its key is not covered. Use `SecureAgentConfig`, whose state lives under its provider `source_id`. These keys
  are protected from request state only: never add them to `_RESERVED_SERVICE_SESSION_STATE_KEYS` or
  `service_session_state_keys`, which also drop them from private Session Continuation State and would discard the
  server's own context label.
- `confirm_changes` snapshot cleanup resolves the synthetic confirmation back to its original `function_call_id`;
  it must never concatenate unrelated tool results or record accepted changes without a matching real result.
- Configured stateless agent Thread Snapshot stores persist after function/MCP tool-result and approval safe points,
  then persist the terminal state. Never treat a yielded `finish_reason` or a following metadata update as successful
  model-turn finalization: inner finalizers and result hooks may still reject that output. Save only after the complete
  result/approval update and lifecycle side effects are applied, and project only completed call/result groups and
  current approval controls into the intermediate snapshot. Sibling text, reasoning, and unrelated pending calls remain
  terminal-only. Do not write every text delta or schedule unordered background snapshot writes. Service-session and
  workflow Thread Snapshots retain terminal-save cadence so replayable messages cannot advance without matching
  provider continuation state; workflow checkpoints own incremental workflow runtime state.
- Disconnect-safe execution is endpoint-owned and opt-in through
  `add_agent_framework_fastapi_endpoint(detached_runs=True)`. Keep its producer queue bounded, retain and observe
  producer/drainer tasks, and let the producer own final snapshot/checkpoint/approval persistence after the SSE reader
  disconnects. Bound endpoint-wide producer admission and cancel abandoned producers after the configured timeout.
  This mode discards unread events; it is not a resumable event log.
- While a detached mutation is active, the endpoint may serve an empty Snapshot Hydrate Request but must reject another
  mutation for the same `(Snapshot Scope, threadId)` with HTTP 409. Classify hydration once and keep it on the direct
  response path so it bypasses detached admission and producer wrapping. Endpoint admission, agent hydration, and
  workflow hydration must all use `_run_common._is_snapshot_hydration_request`; pass workflow checkpoint capability
  explicitly so checkpoint resumes never become hydration. The guard is process-local and does not replace cross-replica
  coordination.
- Detached runs may outlive FastAPI request-scoped disposable resources. Resolve authorization and Snapshot Scope before
  spawning the producer, and do not rely on request-owned clients or sessions remaining open after disconnect.
- SSE keepalive is endpoint-owned transport behavior configured through
  `add_agent_framework_fastapi_endpoint(keepalive_seconds=...)`. It emits SSE comments only; do not add `PING`,
  `HEARTBEAT`, or `KEEPALIVE` AG-UI events, and do not add runner-level keepalive settings.
- AG-UI multimodal request content accepts only web/data URLs and inline payloads. Do not pass file, FTP,
  application-defined URI schemes, or unresolved client-owned `id`/`file` references into provider clients; broader
  outbound access and binary-reference resolution require an application-owned policy. Backend-loaded legacy Thread
  Snapshots replace previously accepted unsupported media parts with inert placeholder text before hydration or
  provider replay, so strict current-request validation does not brick an existing thread.

## Usage

```python
from agent_framework.ag_ui import add_agent_framework_fastapi_endpoint
from fastapi import FastAPI

app = FastAPI()
add_agent_framework_fastapi_endpoint(app, agent, single_user=True)
```

## Import Path

```python
from agent_framework.ag_ui import AGUIChatClient, add_agent_framework_fastapi_endpoint

# or directly:
from agent_framework_ag_ui import AGUIChatClient
```
