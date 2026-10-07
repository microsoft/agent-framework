# Foundry Hosting

This package provides the integration of Agent Framework agents and workflows with the Foundry Agent Server, which can be hosted on Foundry infrastructure.

## Agent instances and factories

`ResponsesHostServer` and `InvocationsHostServer` accept an agent instance or a zero-argument callable through the
existing `agent` parameter. The callable may be synchronous or asynchronous, must return an object implementing
`SupportsAgentRun`, and is invoked once for each request:

```python
server = ResponsesHostServer(agent=create_agent)
```

Passing an instance reuses that object for the lifetime of the host. Pass a callable when the agent keeps mutable state
outside `AgentSession`. A `WorkflowAgent` wraps a stateful workflow, so a `WorkflowAgent` instance is rejected at host
construction: pass a callable that builds a new workflow, executors, and wrapped agents on every call. The host also
rejects a callable that returns the same `WorkflowAgent`, workflow, executor, child workflow, or wrapped agent object
for a later request. Keep the
workflow name and executor IDs stable so later requests can find and restore its checkpoints:

```python
def create_agent():
    return build_workflow().as_agent()


server = ResponsesHostServer(agent=create_agent)
```

The Responses host continues regular agents through its existing session store and workflow agents through its
existing checkpoint store. A callable does not make arbitrary instance fields persistent; state needed by later
requests must remain in the supported stores.

## Native Responses workflows

Use `workflow=` to host a built `Workflow` directly, without `.as_agent()`.
`parse_response` is required and returns exactly one typed start input or a
complete batch of validated pending replies:

```python
from pydantic import BaseModel

from agent_framework_foundry_hosting import (
    CheckpointStoreProvider,
    HostedResponseRequest,
    ResponsesHostServer,
    WorkflowTurn,
)


class Ticket(BaseModel):
    text: str


def build_workflow(request: HostedResponseRequest):
    return build_fresh_graph()  # stable workflow/executor IDs; fresh mutable resources


async def parse_response(request: HostedResponseRequest) -> WorkflowTurn[Ticket]:
    items = await request.get_input_items()
    if any(item.get("type") in ("function_call_output", "mcp_approval_response") for item in items):
        return WorkflowTurn(responses=await request.get_workflow_responses())
    return WorkflowTurn(input=Ticket.model_validate_json(await request.get_input_text() or ""))


ResponsesHostServer(
    workflow=build_workflow,
    parse_response=parse_response,
    checkpoint_store_provider=CheckpointStoreProvider(
        allowed_checkpoint_types=[f"{Ticket.__module__}:{Ticket.__qualname__}"],
    ),
)
```

A direct built workflow is single-use. Use a request-aware sync or async
factory for continuation, approval/user-input pauses, or background recovery.
The factory must return a freshly built graph and freshly owned executors,
agents, clients, context providers, and mutable tools; hosting rejects known
sharing rather than cloning or unwrapping it. Workflow names and executor IDs
must remain stable so the exact scoped checkpoint can be restored.

Native workflow state is scoped to the trusted platform user plus Foundry
sandbox. Each outer stored `response.id` is bound to its exact MAF checkpoint,
graph identity, lineage, pending reply authority, output, and usage. The host
never chooses an unrelated latest checkpoint. Named conversations and
`previous_response_id` continuations advance one conditional head; stale,
forked, replayed, partial, duplicate, forged, cross-user, and cross-sandbox
replies fail before execution.

`store=False` writes no native host state or inner service history and rejects
a pause that would require later resumption. Native `Agent` executors receive
request options through the existing agent middleware boundary, with supported
inner clients forced to `store=False`. A bare `RawAgent` is accepted only from a
fresh factory when its model overrides are already materialized in unchanged
defaults and a storing client explicitly defaults to `store=False`. Private
provider continuation is rejected before output is paired or committed.

For legacy message-input workflows, `response_input_messages(request)` converts
only the current Responses turn to `list[Message]`. It does not load outer
history or decode pending replies. Legacy `agent=` hosting of a `WorkflowAgent`
remains for this beta only through a factory such as
`agent=lambda: build_workflow().as_agent()`, with a once-per-host deprecation
warning; passing a `WorkflowAgent` instance is rejected. Wrapper context
providers, history, event projection, and request-info translation are real
semantics and are not silently unwrapped.

With `resilient_background=True`, the application must also enable the
AgentServer resilient task subsystem. Host-owned checkpoint/output pairs
recover emitted output and usage without selecting newer unpaired workflow
state. This is not an exactly-once guarantee for external tools: make
side-effecting operations idempotent. Legacy unscoped workflow state is not
read; migration starts a fresh Responses chain.

For Responses integrations, use a factory when a provider, tool cache, client or
credential carries request identity or needs request-owned cleanup.
`FoundryToolbox` resolves platform headers at each operation boundary and
rebinds its MCP session when that identity changes, so a long-lived Toolbox does
not retain the first request's call ID. The integration samples still construct
it inside the factory because they also own request-scoped clients, credentials
and providers.

Factory agents are entered/exited for each request, including failed entry and
cancellation. `Agent` manages context-managed clients and MCP tools, but it does
not automatically manage every context provider or external credential. The
[integration samples](../../samples/04-hosting/foundry-hosted-agents/) explicitly
own their SDK transports, credentials and providers: Search is request-owned;
Memory binds a fresh provider/project client to the trusted user and current call;
custom Cosmos state uses user **and** sandbox namespaces with conditional writes.
Only close resources that the factory creates and owns, never a supplied shared
client or somebody else's credential.

## Responses agent history and storage

The caller's `POST /responses` **`store` flag** controls whether the *outer* response is retrievable and whether
MAF session and approval state is saved. The host's `history_source` independently selects who supplies model history:

| `history_source` | What the model receives | Inner storage on caller `store=True` |
| --- | --- | --- |
| `"agent_server"` (default) | Prior outer Responses transcript plus new input | Disabled. Storing clients run with `store=False`; non-storing clients receive no storage option. |
| `"service"` | New input only | Enabled. The service-issued `AgentSession.service_session_id` is saved privately under the outer response ID or conversation. |
| `"agent"` | New input only; the agent chooses how to load history | Developer-owned: `HistoryProvider` with `default_options={"store": False}` loads from host-persisted `AgentSession.state`, **or** a storing client with `default_options={"store": True}` uses downstream service history. The existing behavior is unchanged. |

For example, suppose the first stored response answers **"My name is Ada"**, then the caller sends
**"What is my name?"** with `previous_response_id` set to that response's **outer** `response.id`:

- **`"agent_server"`:** The model receives the first user input, the first assistant output, and the new
  question. The host reconstructs that transcript from the Responses store; the inner service
  does not retain it.
- **`"service"`:** The model receives only the new question as *request input*, along with the
  private `AgentSession.service_session_id` from the first turn. The downstream service retrieves
  its own transcript. A second branch from the first response cannot safely reuse that service
  thread and is rejected.
- **`"agent"`:** The model receives the new question. With `InMemoryHistoryProvider` and agent
  default `store=False`, the provider adds earlier messages from the saved MAF session; with agent
  default `store=True`, the downstream service owns the prior transcript instead.

All three still return **outer** Responses IDs for retrieval and background polling. `store=False`
requests are one-shot: they do not write host-managed state or ask the inner client to store, so
they cannot establish a persistent provider thread. Neither an outer `response.id` nor
`agent_session_id` should be used as an inner `service_session_id`.

Choose **one** mode when constructing each host; do not reuse the same `Agent` instance across hosts.
For example, to use downstream service history:

```python
server = ResponsesHostServer(agent=agent, history_source="service")
```

Omitting `history_source` selects `"agent_server"`. To use a provider in `"agent"` mode,
configure that agent with `store=False` as shown in
[agent_history.py](../../samples/04-hosting/foundry-hosted-agents/responses/basic/agent_history.py).

`"agent_server"` and `"service"` reject a load-enabled `HistoryProvider` alongside their own history source;
`"agent_server"` also rejects default downstream continuation IDs. Those modes require a `RawAgent` with a client declaring
`STORES_BY_DEFAULT`; `"service"` requires a storing client that returns a private continuation ID. Hosting may
add a transient in-memory provider to support function-call loops, but **never edits `agent.default_options`**.
The host owns the provided agent instance and any providers it adds; do not reuse it with another host. A factory
creates an independent agent for each request.

The existing `history_source="agent"` still preserves the agent's own provider **or** service storage defaults
on stored requests, including `default_options={"store": True}`. Custom `SupportsAgentRun`
implementations can continue using that mode for stored requests; it is not a forced-provider mode.
The outer storage-backend constructor argument is now `response_store=`. The old `store=` backend
argument remains an alias with its own once-per-host deprecation warning; supplying both is an error.
Neither constructor argument sets the caller's per-request `store` flag.

`store=False` returns a one-shot response without **writing** host-managed session, conversation, or approval state;
it also disables downstream service storage regardless of the developer's defaults. Unsafe custom agents, external
history providers that store messages, and fixed downstream continuation defaults fail with an actionable error
instead of silently persisting. An unstored service-mode request cannot resume a private service thread.
`history_source="agent"` also rejects an unstored continuation if its restored session uses downstream storage. Application-owned
tools and external services may still have their own side effects. `background=True` requires outer `store=True`.

Outer background work always uses the caller-visible `response.id` for polling; it does not enable provider-native
background automatically. `background_source="agent_server"` (default) uses only the outer background worker.
`background_source="provider"` is a separate opt-in for `history_source="service"` with a storing
Responses client. Its private continuation token is saved under the outer ID and never returned to the caller.
Use `ResponsesServerOptions(resilient_background=True)` to permit recovery from a **saved** token; a crash before
the token is saved cannot safely restart the inner job. Completed polling output, including local function calls,
results, and usage, is saved together with the next token in the private response-ID snapshot before emission.
Outer output checkpoints record which saved batches have been emitted, so recovery restores their usage and
replays only uncheckpointed output. Once the final output is saved, recovery can finish from that snapshot without
calling the provider again; a later turn drops it from its working session. Shutdown during initial submission
fails rather than replaying a job whose acceptance is unknown. Cancelling an in-flight submission does not prove
the remote provider stopped it.
Each poll retains the caller's generation options and `background=True`, so a tool-loop follow-up requests
another background response and saves its next token. A crash after a local tool side effect but before that
next token is saved can still repeat the tool on recovery; use idempotent tools or avoid provider background
for side-effecting local tools. This mechanism does not provide exactly-once tool execution.
Provider background and steering cannot be combined.
Regular agent runs without this opt-in are not crash-replayable. **Steering is temporarily unavailable:**
`steerable_conversations=True` fails during host construction, before enabling the process-wide TaskManager.
The current AgentServer SDK retains unbounded futures for rejected turns when its steering queue fills. Do not
use a queue-length precheck: another worker can append before it. The guard can be removed only after
[Azure/azure-sdk-for-python#49233](https://github.com/Azure/azure-sdk-for-python/pull/49233) ships in an
official `azure-ai-agentserver-core` wheel, the minimum dependency and `uv.lock` are updated, and a
concurrent queue-overflow regression proves rejected turns leave no pending futures. No future SDK
version is assumed. Non-steerable background polling and legacy `WorkflowAgent` dispatch are unchanged.

Native CreateResponse generation fields become MAF runtime options (notably `max_output_tokens` -> `max_tokens` and
`parallel_tool_calls` -> `allow_multiple_tool_calls`). Flattened OpenAI `extra_body` fields overlay translated keys
**last**. A sync or async `prepare_options(request: HostedResponseRequest, options: dict)` hook can remove or replace
*caller* options before `Agent.run`; removed values fall back to the developer's unchanged agent defaults. Hosting
filters caller platform IDs and private continuation/storage controls from model options and rejects attempts to
reintroduce them through the hook. Nested `extra_body` transport overrides are rejected for both caller
input and developer hooks, because they could override the host's `store=False` after the OpenAI SDK merges
the body. Developer defaults also cannot use this transport channel for host-controlled fields on
explicit history modes or unstored requests. A custom agent cannot accept MAF runtime options: choose
`unsupported_options` as `"ignore"`, `"warn"` (default), or `"error"` for that case. See the
[agent history and options samples](../../samples/04-hosting/foundry-hosted-agents/responses/basic/).

### OAuth consent origin allowlist

OAuth consent links keep their existing absolute-HTTPS safety validation. Hosts that know the expected authorization
origins can add an exact origin allowlist:

```python
server = ResponsesHostServer(
    agent,
    allowed_oauth_consent_origins=[
        "https://logic-region.consent.azure-apihub.net",
        "https://auth.partner.example",
    ],
)
```

An omitted allowlist preserves existing behavior and does not restrict the HTTPS origin. A provided allowlist activates
the gate, so an empty sequence rejects every consent link. Entries are normalized as origins, so paths and query strings
belong on the emitted consent link, not in the configuration.

## Computer use

The Responses host emits native `computer_call` and `computer_call_output` items, including ordered `actions`,
screenshots, and typed safety checks. It restores those items from request input and prior response history as
`Content.from_computer_tool_call(...)` and `Content.from_computer_tool_result(...)`. The application must review
`pending_safety_checks` before executing actions and return a screenshot `Content` with explicit
`acknowledged_safety_checks`; the host never acknowledges checks automatically. Results correlate to calls by
`call_id`. When an upstream provider's item ID does not meet AgentServer's ID format, the host assigns a valid
output item ID without changing the provider's `call_id`.
Although screenshots are optional in shared `Content`, this Responses host requires them on computer results.
The computer-use `Content` constructors and `ComputerSafetyCheck` type are experimental Agent Framework APIs.

## State store

### Local persistence

Outside the Foundry hosting environment, state is persisted as JSON files under
`~/.agentserver/state_stores` by default. Set `AGENTSERVER_STATE_ROOT` to use a
different root directory; the files will be written to its `state_stores`
subdirectory instead.

Each logical store is saved as one JSON file whose name is a URL-safe Base64
encoding of the store name. For example:

- Responses agent sessions: `YWdlbnRfc2Vzc2lvbnM.json`
- Function approvals: `ZnVuY3Rpb25fYXBwcm92YWxz.json`
- Workflow checkpoints: one file per context, encoded from `checkpoints/<context_id>`

> Read more about the Foundry durable state store in the [developer guide](https://github.com/Azure/azure-sdk-for-python/blob/main/sdk/agentserver/azure-ai-agentserver-core/docs/state-store-guide.md).

### User isolation

Hosted requests require platform user and call IDs from the AgentServer request
context. Responses also requires the platform-configured `FOUNDRY_AGENT_SESSION_ID`
(`AgentConfig.session_id`) for sandbox identity; a different caller-supplied
`agent_session_id` fails closed. For Invocations, the
[platform routes by the `agent_session_id` query parameter](https://learn.microsoft.com/azure/foundry/agents/how-to/manage-hosted-sessions#how-each-protocol-binds-an-invocation-to-a-session).
When `FOUNDRY_AGENT_SESSION_ID` is present, it must match that query and the
resolved request context. When it is absent, only an explicit, nonempty routed
query matching the request context can identify the sandbox; duplicate query
IDs or a request without the query are rejected rather than using the SDK's
generated fallback ID.
This means an automatically created first Invocations session without a query
cannot access default hosted state when the platform does not configure the
session ID. The platform documentation does not guarantee that the environment
variable is provided for every sandbox.

`FoundryRequestScope.from_context(config, platform_context)` requires the
configured ID and remains strict for Responses and direct store providers. Only
the Invocations host accepts the verified routed-query alternative. Its
`storage_key` is a bounded hash of the framed user and sandbox IDs, not a caller
conversation or response ID.

| Identifier | Purpose |
| --- | --- |
| Foundry session ID | Platform sandbox for the hosted request and its MAF state. |
| Platform user ID / call ID | User isolation and per-request storage authorization/correlation. A call ID is **not** a conversation ID. |
| Responses `response.id`, `previous_response_id`, `conversation` | Caller-visible continuation and conversation IDs, used as item keys *within* the sandbox. |
| MAF `AgentSession.session_id` / `service_session_id` | Inner agent state and optional downstream service continuation; neither identifies the Foundry sandbox. |
| Workflow checkpoint ID | Inner workflow state within a checkpoint context, not a Foundry session ID. |

The default hosted MAF session, checkpoint, and approval stores use a `v2` namespace
derived from the hashed platform identity, with `user_isolation=True` and an explicit
platform `call_id` on each item operation. Checkpoint context IDs are hashed as well.
The same user in two hosted sandboxes cannot read the other's default MAF state.
Locally, the existing single-user store names and file-based fallback remain unchanged;
direct store constructors without a trusted `scope` also retain their existing local
behavior. Applications that supply custom store providers must implement equivalent
hosted user and sandbox isolation.

**Existing hosted state is not migrated.** The default stores never fall back to
legacy unscoped `agent_sessions`, `invocation_sessions`,
`checkpoints/<context_id>`, or `function_approvals` data: an old MAF session,
workflow checkpoint, or pending approval cannot be resumed through the new
default hosted stores. Start a fresh Responses conversation rather than reusing
an old `previous_response_id` or conversation ID; Invocations starts with an
empty MAF session in its scoped store. The separate AgentServer response store
is not migrated by this change. Recovering old state requires a separately
designed migration that verifies the original user's and sandbox's ownership;
reading unscoped data by user alone is not safe.

### Agent Sessions

`ResponsesHostServer` and `InvocationsHostServer` persist the Agent Framework `AgentSession`
durably. By default they use `FoundryAgentSessionStore`, backed by Foundry storage when hosted
and file-based storage locally. Responses sessions use the `agent_sessions` logical store;
Invocations sessions use the separate `invocation_sessions` store.

Each stored agent turn saves a snapshot under its **own** outer `response.id`. For a named `conversation`, a
separate mutable conversation-head key is also updated. Loaded MAF sessions use PR1's ETag condition for that key:
a competing turn that advanced the head causes a visible conflict rather than a stale overwrite. A superseded
steered turn saves its response snapshot but skips the head update. In `"service"` or `"agent"` history mode, a
stored named-conversation turn first claims that head with a conditional write *before* calling the inner agent.
Another request that read the old head loses the CAS; one that reads the claim fails before touching the provider.
The claim is cleared when the winning turn successfully commits the new head. If a dispatched turn fails or is
cancelled, the claim remains: the provider may already have changed its thread, so start a new conversation
instead of retrying this one blindly. A recovered provider-background turn must still own the same claim.
The committed head also records its completing outer response ID. If a crash occurs after the head write but before
outer completion, that response can recover its saved final output without reclaiming or rewriting the head.
A different in-flight claim or completing response is not accepted as ownership.
When continuing by `previous_response_id`, the prior response is claimed with a conditional write **after**
the input is validated, so an invalid approval response does not consume a usable parent. A second branch
cannot reuse the same downstream service thread; attempting to fork a named service conversation is also rejected.
New hosted keys are created only if absent. Custom store providers must provide equivalent scoped conditional
writes for concurrent turns, including the pre-dispatch claim. Local callers can still upsert directly without
first loading a session.

See the [custom storage provider sample](../../samples/04-hosting/foundry-hosted-agents/responses/custom_storage/)
for an example that uses an in-memory session store locally and Azure Cosmos DB when hosted.

Native Responses refusal parts are stored as text carrying
`additional_properties["model_output_kind"] == "refusal"` and emitted as
`response.refusal.*` events when streamed back to clients.

`InvocationsHostServer` restores sessions from its configured store. When hosted, `AgentSession.session_id` is an
opaque composite identifier that preserves the boundaries between the platform session ID
and user ID. Consumers must use it as a whole and must not parse it or depend on its internal
representation. Repeated requests for the same identifier pair restore the saved session.
Locally, the platform session ID is used unchanged.

### Invocations agent requests and wire compatibility

By default, `POST /invocations` accepts `{"message": "Hi", "options": {}, "stream": false}`. Applications can supply
a sync or async `parse_request(request)` returning a typed `InvocationRun(messages, options, stream)` to accept their
own JSON shape and MAF `Message` inputs. A sync or async `prepare_options(request, options)` hook can filter or replace
a **copy** of this turn's caller options without changing the agent's `default_options`. It must return a mapping
with string keys. The host rejects reserved platform/session fields, `store`, `extra_body`, and private continuation
fields after the hook; callers cannot select another sandbox or enable downstream service continuation through
runtime options. It also rejects agent execution controls: `additional_function_arguments`, `function_invocation_kwargs`,
`client_kwargs`, `middleware`, `session`, `tools`, `instructions`, `compaction_strategy`, and `tokenizer`. Trusted tool
arguments belong in developer-configured agent defaults or middleware/factories, not in request options or hook output.
A hook may strip denied caller fields before validation; allowed generation and provider-specific options remain
available. These restrictions apply to both wire formats and every `unsupported_options` policy.
When an agent cannot accept runtime options, `unsupported_options="warn"` (default) logs and ignores
them; `"ignore"` silently drops them and `"error"` rejects them. For request-scoped factories, unsupported options
discovered after streaming starts are reported as an SSE `error` event with `status: 400`.

**New default:** non-streaming success is JSON `{"response": "..."}`. Streaming success is real SSE
`event: delta` with `{"text": "..."}`, followed by `event: done` with the platform sandbox `session_id`.
The `done` event is sent only after the final MAF `ResponseStream` is finalized and the session is persisted.
Client validation errors return JSON HTTP 400 before streaming where possible. Provider errors are logged and
sanitized as JSON HTTP 500 or an SSE `error`; a cross-process ETag conflict is JSON HTTP 409 or an SSE `error`
with `code: "session_conflict"` and `status: 409`. A stream may emit deltas before an error. The host serializes
same-session requests in one process, but a CAS conflict can still follow external tool effects in separate
processes; it does not guarantee exactly-once execution. See the
[Invocations agent/parser example](../../samples/04-hosting/foundry-hosted-agents/invocations/basic/).

**Deprecated opt-in:** set `InvocationsHostServer(agent, legacy_wire_format=True)` only for existing clients
that must keep the previous plain-text non-streaming response and raw text-chunk streaming format. The host logs
and emits a deprecation warning once on construction. Errors are never returned as successful text: non-stream
failures still use JSON error statuses; a post-start legacy stream failure terminates the stream rather than
injecting unexpected SSE framing. Migrate all opted-in clients to JSON/SSE; remove the compatibility mode only
after those callers have migrated and a separate, deliberate breaking-change decision, never by silently
switching an opted-in deployment.

Both hosts accept `agent_session_store_provider` to select a `StoreProvider[SessionStore]`.
Session state must support `AgentSession` serialization. Use `register_state_type()` codecs for
custom types; unsupported live objects fail during persistence. Restored sessions preserve
state, not Python object identity. New default stores expire saved sessions 30 days after
their last write; an invocation after expiry starts a fresh session.
Existing stores retain their creation-time settings, and custom providers own their retention
policies.

Default hosted stores reject stale ETag and duplicate-create writes for
overlapping turns instead of overwriting a newer MAF session. This does not
provide transactions or exactly-once execution for agent/tool side effects;
applications still need to coordinate overlapping requests. Independent local
applications should use separate state roots or store providers.

### Workflow checkpoints

`ResponsesHostServer` persists workflow checkpoints durably. By default, it uses the
`FoundryCheckpointStore`, backed by Foundry storage when hosted and file-based storage
locally. Stored checkpoints are scoped under `checkpoints`.

### Function approvals

`ResponsesHostServer` persists function approvals durably. By default, it uses the
`FoundryFunctionApprovalStore`, backed by Foundry storage when hosted and file-based
storage locally. Stored approvals are scoped under `function_approvals`.

## Native Invocations workflows

Host a native workflow with an explicit application parser rather than wrapping it
with `workflow.as_agent()`:

```python
server = InvocationsHostServer(
    workflow=build_workflow,
    parse_request=parse_request,
    checkpoint_store_provider=CheckpointStoreProvider(
        allowed_checkpoint_types=["my_app:Ticket", "my_app:TicketState"]
    ),
)
```

The sync/async parser receives the raw Starlette `Request` and must return either
`WorkflowTurn(input=typed_input, stream=...)` or
`WorkflowTurn(responses={request_id: typed_reply, ...}, stream=...)`. There is no
default workflow JSON schema. Validate your application input and reply types,
including duplicate fields or decisions, in the parser; the host additionally
validates the entire reply batch against its exact pending checkpoint.

A sync/async `build_workflow(request)` factory returns a **built**, fresh `Workflow`,
with stable name, executor IDs and graph identity. Build fresh executors, agents,
clients, providers and tools for each request; allocation must not execute tools or
workflow side effects. Hosted workflows require a factory. Local built instances
are single-use and remain application-owned. Factory-owned agents are entered and
closed per turn; applications must explicitly own external credentials/providers
through their resource-managing agent subclasses. Do not configure another
checkpoint store on `WorkflowBuilder` or share mutable graphs between requests.

Native `AgentExecutor` graphs support `Agent` and constrained bare `RawAgent`.
For `Agent`, hosting applies options through a request-owned agent middleware
policy, disables inner service storage and preserves the developer's defaults.
A bare `RawAgent` must come from a validated fresh factory with a client declaring
its storage capability. A storing raw client requires explicit factory default
`store=False`; requested model overrides must already be materialized and matched
in that fresh agent's defaults. Unsafe/custom agents, mismatched overrides and
unexpected downstream continuation are rejected before successful output or
commit. The host never forwards duplicate `options=` through client kwargs, and
caller JSON cannot assert factory ownership.

The workflow uses one fixed Invocations lineage inside the trusted user and
platform sandbox scope. Later turns restore the **exact** committed checkpoint,
not a workflow name's unrelated latest checkpoint. Graph changes, stale writers,
forged/cross-scope/replayed decisions and duplicate authority fail before
executor/response-handler dispatch. Reply with the complete pending batch:
partial, unallowlisted, or invalid batches do not claim or consume any usable
authority, so the complete valid batch can be retried. Native factories
and explicit `client_kwargs`/`function_invocation_kwargs` keep their existing
purposes; they do not introduce arbitrary entry-state or per-executor run-option
APIs. Host-controlled identity, storage and execution controls cannot be supplied
as caller generation settings.

Non-streaming responses are JSON `{"output": [...]}` containing typed `output` and
`request_info` event objects. JSON primitives, dataclasses, Pydantic models and
framework `Message`, `Content` and response values retain their supported encoding.
All nested mappings, including mappings returned by model/dataclass/framework
serializers, require string keys before JSON conversion so key coercion cannot
silently collide. Private provider continuation tokens are omitted;
unsupported/nonfinite/circular values fail explicitly. Streaming emits framed
`output`/`request_info` SSE,
then `done` with the **sandbox** `session_id`. Live output is provisional until
`done`; pending authority and following frames are buffered until the exact cursor
is conditionally committed. Snapshot retention is bounded by both event count and
encoded bytes; exceeding either limit fails the turn without `done`. A conflict,
encoding failure, execution failure or
interruption cannot emit successful completion. Failed claimed turns are blocked
to avoid replaying uncertain effects; start a new sandbox instead of blindly
retrying non-idempotent work. Checkpoints do not provide exactly-once tool effects.
If a connection drops after commit, retrying the same trusted user/sandbox/call ID
replays that response's complete stored snapshot without executing the workflow or
replacing its head. A different call ID starts normal turn validation and cannot
retrieve that snapshot.
Local callers may pass one built workflow for a one-shot non-pausing run. Any
workflow that can pause for external input must use a request-aware factory so a
fresh graph can restore and consume the durable reply on the next request.
After a newer Invocations head is durably committed, the host reclaims completed
ancestor response records and checkpoints oldest-first, retaining only current,
pending, active or blocked authority. Cleanup failures are logged and retried by
a later successful turn without changing the already committed result; default
store expiry remains a backstop. Custom checkpoint providers own their conditional
delete and retention behavior.

The existing Invocations sandbox-routing and trusted user/call requirements apply,
including the verified `agent_session_id` query alternative when the platform
does not configure `FOUNDRY_AGENT_SESSION_ID`. Body/header IDs cannot establish
sandbox routing or select private checkpoints. The agent path still uses its
separate `invocation_sessions` store, existing hooks/defaults and JSON/`delta` SSE
contract. Agent-only `legacy_wire_format=True`, `prepare_options` and
`agent_session_store_provider` are rejected for native workflows rather than
silently reinterpreted.

See the [typed Ticket/review example](../../samples/04-hosting/foundry-hosted-agents/invocations/basic/README.md#native-workflow-with-typed-tickets)
for the parser, stable graph, checkpoint type allowlist, pending replies,
JSON/SSE and local/hosted migration guidance.
