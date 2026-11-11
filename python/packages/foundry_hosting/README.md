# Foundry Hosting

This package provides the integration of Agent Framework agents and workflows with the Foundry Agent Server, which can be hosted on Foundry infrastructure.

See [ADR 0055](../../../docs/decisions/0055-python-foundry-hosting-contracts.md) for the design rationale.

## Choose the host

Use `ResponsesHostServer` or `InvocationsHostServer` for agents. Use
`ResponsesWorkflowHostServer` or `InvocationsWorkflowHostServer` for native workflows.
Each workflow host requires a request-aware sync/async factory and an explicit parser.
All four hosts remain in `agent-framework-foundry-hosting`, with matching lazy exports
under `agent_framework.foundry`. The package is currently in beta, so its public APIs are
experimental. Responses hosting is the target for an initial stable release, subject to
qualification. Invocations hosting and `FoundryToolbox` remain experimental.

**Breaking migration:** replace `ResponsesHostServer(workflow=..., parse_response=...)` with
`ResponsesWorkflowHostServer(workflow=..., parse_input=...)`, and replace
`InvocationsHostServer(workflow=..., parse_request=...)` with
`InvocationsWorkflowHostServer(workflow=..., parse_input=...)`.
There is no combined-host compatibility shim. Agent host construction still uses `agent=`.
All custom parsers now use `parse_input`, including agent parsers on `InvocationsHostServer`.
Rename `HostedResponseRequest` imports and annotations to `ResponsesRequest`, including factories and option hooks.
`InvocationRun` and `WorkflowTurn` are unchanged. Workflow parsers still adapt either typed start input
or a complete batch of pending replies; they are not limited to initial input or raw JSON deserialization.
The old parser keywords and request-type name have no compatibility aliases.

**Caller-options migration:** caller model-run options are no longer forwarded by default.
For Responses agents, Responses workflows, and Invocations agents, configure `prepare_options`
to select the options the application accepts. Only the hook's returned, validated mapping is forwarded.
Without a hook, agent/client defaults still apply. Responses agent factories see translated caller
options before the hook; native Responses workflow factories see options after the hook.
The original request remains available to application code.

Agent history/background source literals also change without aliases:

| Setting | Previous literal | New literal |
| --- | --- | --- |
| `history_source` | `"agent_server"` | `"host_managed"` |
| `history_source` | `"agent"` | `"agent_managed"` |
| `history_source` | `"service"` | `"inference_service"` |
| `background_source` | `"agent_server"` | `"host_managed"` |
| `background_source` | `"provider"` | `"inference_service"` |

These are terminology changes only. The default remains host-managed history and background execution.
`agent_managed` retains developer-owned provider **or** service storage, not just `HistoryProvider` storage.
`response_store=` and the wire-level `store` flag keep their existing meanings.
The deprecated constructor `store=` backend alias is removed. Replace it with `response_store=`;
even `store=None` is rejected. This does not rename the caller's per-request `store` flag.

`WorkflowSource` now describes a factory only; passing a built workflow fails at construction,
including local one-shot use. Move graph and executor construction inside the factory;
returning a new wrapper around shared executors does not isolate execution state.

Workflow hosts expose checkpoint storage, not agent-session storage or agent history/background
policies. Responses workflows retain `prepare_options`; Invocations workflows use the parser's
explicit workflow kwargs instead. Agent approval persistence follows the
[session-store contract below](#function-approvals).
Agent hosts reject `WorkflowAgent`, whether supplied directly or returned by a factory.
`checkpoint_store_provider` is available only on workflow hosts.
No stored state is converted between native workflow and agent execution models.

## Explicit host configuration

Configure inference defaults on the agent or client, not on the host. Supported hosting settings are:

| Setting and default | Applies to | Meaning |
| --- | --- | --- |
| `max_history_items=None` | Responses agents | A positive integer caps prior outer history items, only with `history_source="host_managed"`. `None` leaves the installed SDK default unchanged; it does not mean unlimited. |
| `sse_keep_alive_interval_seconds=None` | All four hosts with framed SSE | A positive integer sets the heartbeat interval in seconds. `None` inherits a positive `SSE_KEEPALIVE_INTERVAL`; an absent or nonpositive environment value disables heartbeats. |
| `shutdown_grace_period_seconds=10` | Both Responses hosts | A positive integer sets shutdown waiting in seconds. The SDK also uses it when DELETE waits for response persistence. It is not a model or request timeout. |
| `enable_background_recovery=False` | Both Responses hosts | A boolean permits eligible background recovery. It does not select background execution or guarantee exactly-once effects. |

For example, after defining the [request-aware factory below](#agent-instances-and-factories):

```python
server = ResponsesHostServer(
    agent=create_agent,
    max_history_items=100,
    sse_keep_alive_interval_seconds=15,
    shutdown_grace_period_seconds=20,
)
```

Explicit integer settings reject booleans and non-integers with `TypeError`, and nonpositive values with
`ValueError`. A positive history cap in another agent history mode emits a warning and is ignored. Workflow hosts reject
`max_history_items`, including explicit `None`; they do not use outer transcript history caps.
Invocations hosts reject the Responses-only settings `history_source`, `background_source`,
`max_history_items`, `shutdown_grace_period_seconds`, and `enable_background_recovery`, even when `None`.
The existing upstream Invocations `graceful_shutdown_timeout` passthrough is a separate setting.

An explicit positive SSE interval takes precedence over a positive environment value. However, the SDK parses
`SSE_KEEPALIVE_INTERVAL` before applying that override: malformed values, including an empty string, still raise
`ValueError` even with an explicit interval. Heartbeats do not set a request timeout.

The public `ResponsesServerOptions` bag is no longer accepted through `options=`. Removed host settings
`default_fetch_history_count`, `default_model`, `create_span_hook`, `additional_server_version`,
`steerable_conversations`, and `resilient_background` also raise `TypeError`, including when `None`.
Use the first-class settings above, agent/client defaults, and Agent Framework observability instead.

| Host | Continuation state | `prepare_options` | Background recovery |
| --- | --- | --- | --- |
| `ResponsesHostServer` | Agent session plus the selected history source | Sync or async | Eligible inference-service background only |
| `ResponsesWorkflowHostServer` | Exact native workflow checkpoint | Sync or async, before `parse_input` | Checkpoint-backed outer recovery |
| `InvocationsHostServer` | Agent session; application-owned model history | Sync or async | No provider-background recovery |
| `InvocationsWorkflowHostServer` | Exact native workflow checkpoint | Not supported; use `WorkflowTurn` kwargs | No provider-background recovery |

These are API support boundaries, not live deployment qualification or a promotion of the experimental
surfaces described above.

## Responses route prefix

`ResponsesHostServer` and `ResponsesWorkflowHostServer` pass `prefix` to the
[AgentServer Responses host](https://learn.microsoft.com/python/api/azure-ai-agentserver-responses/azure.ai.agentserver.responses.responsesagentserverhost?view=azure-python),
so clients and reverse proxies must use the same path prefix for its
[protocol endpoints](https://learn.microsoft.com/python/api/overview/azure/ai-agentserver-responses-readme?view=azure-python#protocol-endpoints).

## Toolbox tool approvals

`FoundryToolbox` uses each discovered tool's `_meta.tool_configuration.require_approval` when
`approval_mode` is omitted or `None`. See the
[Foundry approval configuration](https://learn.microsoft.com/python/api/azure-ai-projects/azure.ai.projects.models.mcptoolrequireapproval)
for supported metadata shapes.

Unlike regular MCP tools, Toolbox `approval_mode=None` does not mean no approval.
Use `"never_require"` to disable local approval or `"always_require"` to require it for every function.
Any explicit non-`None` policy, including a dictionary or callable, replaces metadata handling entirely.
Missing metadata defaults to no approval; malformed metadata raises `ToolExecutionException`.

Metadata filters use remote/original tool names, not local prefixes. Filter criteria must all match;
`always` wins overlaps and unmatched filter-policy tools require approval. Discovery refreshes and reconnects
reapply the policy; failed refreshes preserve the previous complete snapshot and approval modes.

**Trust boundary:** This Foundry-specific integration trusts the supplied `annotations.readOnlyHint`
when evaluating `read_only` filters, including rules that skip approval. It does not independently
verify that classification or enforce read-only behavior. Applications must trust the classifications
supplied through their configured Toolbox. The private metadata parser is intended only for Foundry
Toolbox; reusing it elsewhere provides no security or compatibility guarantees. It is not a
general-purpose MCP approval policy.

## Agent instances and factories

`ResponsesHostServer` and `InvocationsHostServer` accept an agent instance or a callable through the
`agent` parameter. The callable may be synchronous or asynchronous, must return an object implementing
`SupportsAgentRun`, and is invoked once for each request as `factory(request=request)`.
Factories must declare a required parameter named `request`, either keyword-only or positional-or-keyword.
Additional parameters may have defaults, and the factory may ignore the request.
Zero-argument factories and factories with only optional configuration parameters are rejected at construction;
add a required `request` parameter when migrating them. Responses factories receive a
`ResponsesRequest`, with trusted scope, current-turn input helpers, and translated caller options.
They run before `prepare_options`; the hook can subsequently replace those options.
Invocations factories receive the Starlette `Request` after parsing and option preparation.
Factory exceptions are not retried with another call shape.

```python
server = ResponsesHostServer(agent=create_agent)
```

For request-aware construction:

```python
from agent_framework_foundry_hosting import ResponsesRequest, ResponsesHostServer


async def create_agent(*, request: ResponsesRequest):
    return await build_agent_for_user(request.scope.user_id)


server = ResponsesHostServer(agent=create_agent)
```

Passing an instance reuses that object for the lifetime of the host. Pass a callable when the agent keeps mutable state
outside `AgentSession`. Agent hosts continue agents through their session stores. A callable does not make arbitrary
instance fields persistent; state
needed by later requests must remain in the supported stores.

### Migrate `WorkflowAgent` hosting

`ResponsesHostServer` and `InvocationsHostServer` reject `WorkflowAgent` instances and factory results.
Host the workflow natively with a request-aware factory returning a built `Workflow`, not `workflow.as_agent()`.
Workflow hosts also reject factories returning agents. See
[Native Responses workflows](#native-responses-workflows) and
[Native Invocations workflows](#native-invocations-workflows):

```python
# build_workflow(request) returns a freshly built Workflow for each request.
server = ResponsesWorkflowHostServer(workflow=build_workflow, parse_input=parse_input)
```

Build fresh workflows, executors, and agents for every request. Keep the workflow name and executor IDs stable so
later requests can find and restore checkpoints. Existing wrapper history, context providers, and event semantics
are not automatically unwrapped or migrated.

## Native Responses workflows

Use `ResponsesWorkflowHostServer` to host a native `Workflow` through a request-aware factory, without `.as_agent()`.
`parse_input` is required and returns exactly one typed start input or a
complete batch of validated pending replies:

```python
from pydantic import BaseModel

from agent_framework_foundry_hosting import (
    CheckpointStoreProvider,
    ResponsesRequest,
    ResponsesWorkflowHostServer,
    WorkflowTurn,
)


class Ticket(BaseModel):
    text: str


def build_workflow(request: ResponsesRequest):
    return build_fresh_graph()  # stable workflow/executor IDs; fresh mutable resources


async def parse_input(request: ResponsesRequest) -> WorkflowTurn[Ticket]:
    items = await request.get_input_items()
    if any(item.get("type") in ("function_call_output", "mcp_approval_response") for item in items):
        return WorkflowTurn(responses=await request.get_workflow_responses())
    return WorkflowTurn(input=Ticket.model_validate_json(await request.get_input_text() or ""))


ResponsesWorkflowHostServer(
    workflow=build_workflow,
    parse_input=parse_input,
    checkpoint_store_provider=CheckpointStoreProvider(
        allowed_checkpoint_types=[f"{Ticket.__module__}:{Ticket.__qualname__}"],
    ),
)
```

Every native workflow host requires a request-aware sync or async factory,
including local one-shot execution, continuation, approval/user-input pauses, and background recovery.
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
history or decode pending replies. `agent=workflow.as_agent()` is no longer supported.
Wrapper context providers, history, event projection, and request-info translation are
not silently unwrapped. See [Migrate `WorkflowAgent` hosting](#migrate-workflowagent-hosting).

With `enable_background_recovery=True`, the application must also enable the
AgentServer resilient task subsystem. Host-owned checkpoint/output pairs
recover emitted output and usage without selecting newer unpaired workflow
state. This is not an exactly-once guarantee for external tools: make
side-effecting operations idempotent. Legacy unscoped workflow state is not
read; migration starts a fresh Responses chain.

### Factory resource lifecycle

For Responses integrations, use a factory when a provider, tool cache, client or
credential carries request identity or needs request-owned cleanup.
`FoundryToolbox` resolves platform headers at each operation boundary and
rebinds its MCP session when that identity changes, so a long-lived Toolbox does
not retain the first request's call ID. The integration samples still construct
it inside the factory because they also own request-scoped clients, credentials
and providers.

The host unwinds successfully entered factory-agent contexts when a request
finishes, fails or is cancelled. `Agent` also unwinds client and MCP contexts
it has entered if a later context fails to enter. Allocations made before agent
entry and partial allocations from a failed client `__aenter__` may not be
cleaned up. Calling `agent.close()` before entry does not dispose an unentered
client.

`Agent` manages context-managed clients and MCP tools, but it does not
automatically manage every context provider or external credential. Exiting an
entered `Agent` can close a caller-supplied context-managed client; ownership
depends on the client's context contract. The host cannot reliably identify a
shared client on first use, so applications must ensure that shared clients
support the agent's entry and exit behavior. The
[integration samples](../../samples/04-hosting/foundry-hosted-agents/) explicitly
own their SDK transports, credentials and providers: Search is request-owned;
Memory binds a fresh provider/project client to the trusted user and current call;
custom Cosmos state uses user **and** sandbox namespaces with conditional writes.

## Responses agent history and storage

The caller's `POST /responses` **`store` flag** controls whether the *outer* response is retrievable and whether
MAF session and approval state is saved. The host's `history_source` independently selects who supplies model history:

| `history_source` | What the model receives | Inner storage on caller `store=True` |
| --- | --- | --- |
| `"host_managed"` (default) | Prior outer Responses transcript plus new input | Disabled. Storing clients run with `store=False`; non-storing clients receive no storage option. |
| `"inference_service"` | New input only | Enabled. The service-issued `AgentSession.service_session_id` is saved privately under the outer response ID or conversation. |
| `"agent_managed"` | New input only; the agent chooses how to load history | Developer-owned: `HistoryProvider` with `default_options={"store": False}` loads from host-persisted `AgentSession.state`, **or** a storing client with `default_options={"store": True}` uses downstream service history. The existing behavior is unchanged. |

For example, suppose the first stored response answers **"My name is Ada"**, then the caller sends
**"What is my name?"** with `previous_response_id` set to that response's **outer** `response.id`:

- **`"host_managed"`:** The model receives the first user input, the first assistant output, and the new
  question. The host reconstructs that transcript from the Responses store; the inner service
  does not retain it.
- **`"inference_service"`:** The model receives only the new question as *request input*, along with the
  private `AgentSession.service_session_id` from the first turn. The downstream service retrieves
  its own transcript. A second branch from the first response cannot safely reuse that service
  thread and is rejected.
- **`"agent_managed"`:** The model receives the new question. With `InMemoryHistoryProvider` and agent
  default `store=False`, the provider adds earlier messages from the saved MAF session; with agent
  default `store=True`, the downstream service owns the prior transcript instead.

All three still return **outer** Responses IDs for retrieval and background polling. `store=False`
requests are one-shot: they do not write host-managed state or ask the inner client to store, so
they cannot establish a persistent provider thread. Neither an outer `response.id` nor
`agent_session_id` should be used as an inner `service_session_id`.

Choose **one** mode when constructing each host; do not reuse the same `Agent` instance across hosts.
For example, to use downstream service history:

```python
server = ResponsesHostServer(agent=agent, history_source="inference_service")
```

Omitting `history_source` selects `"host_managed"`. To use a provider in `"agent_managed"` mode,
configure that agent with `store=False` as shown in
[agent_history.py](../../samples/04-hosting/foundry-hosted-agents/responses/basic/agent_history.py).

`"host_managed"` and `"inference_service"` reject a load-enabled `HistoryProvider` alongside their own history source;
`"host_managed"` also rejects default downstream continuation IDs. Those modes require a `RawAgent` with a client declaring
`STORES_BY_DEFAULT`; `"inference_service"` requires a storing client that returns a private continuation ID. Hosting may
add a transient in-memory provider to support function-call loops, but **never edits `agent.default_options`**.
The host owns the provided agent instance and any providers it adds; do not reuse it with another host. A factory
creates an independent agent for each request.

Custom `SupportsAgentRun` implementations can use `history_source="agent_managed"` for stored requests.

`store=False` returns a one-shot response without **writing** host-managed session, conversation, or approval state;
it also disables downstream service storage regardless of the developer's defaults. Unsafe custom agents, external
history providers that store messages, and fixed downstream continuation defaults fail with an actionable error
instead of silently persisting. An unstored service-mode request cannot resume a private service thread.
`history_source="agent_managed"` also rejects an unstored continuation if its restored session uses downstream storage. Application-owned
tools and external services may still have their own side effects. `background=True` requires outer `store=True`.

Outer background work always uses the caller-visible `response.id` for polling; it does not enable provider-native
background automatically. `background_source="host_managed"` (default) uses only the outer background worker.
`background_source="inference_service"` is a separate opt-in for `history_source="inference_service"` with a storing
Responses client. Its private continuation token is saved under the outer ID and never returned to the caller.
Set `enable_background_recovery=True` to permit recovery from a **saved** token; for regular agents it requires
`history_source="inference_service"` and `background_source="inference_service"`. A crash before
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
Regular agent runs without this opt-in are not crash-replayable.

The supported regular-agent combinations for host-selected provider background are:

| `history_source` | `background_source` | Host-selected provider background | `enable_background_recovery=True` |
| --- | --- | --- | --- |
| `"host_managed"` | `"host_managed"` | No; outer background only | Rejected |
| `"agent_managed"` | `"host_managed"` | No; outer background only | Rejected |
| `"inference_service"` | `"host_managed"` | No; outer background only | Rejected |
| `"inference_service"` | `"inference_service"` | Only when the outer request has `background=true` | Supported for saved private tokens |

`background_source="inference_service"` with either other history mode is rejected. All background requests
require outer `store=true`. For checkpoint-backed native Responses workflow recovery, use
`enable_background_recovery=True` and enable the AgentServer resilient task subsystem; agent history/background
source settings do not apply. This does not enable provider background on workflow agents.

The host sets provider `background=True` only for an outer background request with both
`history_source="inference_service"` and `background_source="inference_service"`. In that selected mode,
submission and polling retain `background=True`, even if `prepare_options` returns `background=False`.
On ordinary agent runs, a hook-returned `background` value passes through unchanged. Without a hook-selected
value, inference-service background mode passes `False` for an outer foreground request; other modes omit it.
Invocations agents have no outer background mode and do not add a background option.

An application that selects background in a Responses or Invocations agent hook owns that choice; it does not
enable host-managed provider polling or recovery. Hosting does not inject middleware to inspect or override
background values set by application agent/chat middleware, and adds no Core interception hook.
Factory and developer defaults still undergo background validation before execution. A nested
`extra_body["background"]` in caller options is rejected before the Responses hook, even when it is `False`.

Native workflows keep a separate checkpoint contract: inner provider background is unsupported, and their
option hook cannot select it. Outer workflow `background=True` does not enable it for constituent agents.
A native `WorkflowTurn` rejects client-level and run-level `middleware`.
Its existing native agent options middleware validates transport controls, storage, and unfinished provider
responses to preserve checkpoint ownership; that multipurpose policy remains in place.

**Steering is unavailable.** `steerable_conversations` and the other removed `ResponsesServerOptions` settings are
not host parameters; passing them raises `TypeError` during host construction. The AgentServer SDK can retain
unbounded futures for rejected turns when its steering queue fills
([Azure/azure-sdk-for-python#49233](https://github.com/Azure/azure-sdk-for-python/pull/49233)). Any future
steering support needs a published SDK fix, a dependency update, and a concurrent queue-overflow regression.
No future SDK version is assumed. Agent background polling without steering is unchanged.

### Preparing caller options

Caller model-run options are opt-in. Without `prepare_options`, the host clears the translated option mapping
and does not forward caller generation settings. Agent/client defaults and host-owned storage/background controls
still apply. Application factories can still inspect the original request; this default is not an access restriction.

Native CreateResponse generation fields are translated to MAF runtime options, notably `max_output_tokens` -> `max_tokens`
and `parallel_tool_calls` -> `allow_multiple_tool_calls`. Precedence, from lowest to highest, is:
native generation fields, flattened unknown generation fields, generation fields inside a literal `extra_body`
mapping, then the `prepare_options` replacement. The OpenAI client normally flattens its `extra_body` into the
wire request; a literal nested mapping is also accepted for generation settings.

A sync or async `prepare_options(request: ResponsesRequest, options: dict[str, Any])` hook receives a fresh
deep copy of this turn's effective caller options. It must return a replacement mapping with string keys;
the host deep-copies that result again. Mutating the argument without returning a mapping is invalid.
Removing `"model"` lets the developer's unchanged agent/client model default apply, while other caller
settings such as `"temperature"` remain only if the hook returns them. Return an explicit allowlist to limit
caller control, or return the supplied mapping to opt in to all options that pass validation.
This works for streaming and non-streaming requests.

Responses agent ordering is translation, factory resolution and configuration checks, hook, then protected-option
validation before execution. The factory therefore sees translated options **before** the hook. Invocations
agent ordering is parser, hook, protected-option validation, factory, then default validation before entering
the agent. Do not rely on identical HTTP error timing between protocols. Responses workflows run their hook
before factory resolution and `parse_input`; without a hook their factories see an empty `request.options`,
but can still inspect `request.request`. Invocations workflows have no option hook.

Native request-envelope controls such as identity, storage, and continuation fields are not forwarded as
generation options. Putting those controls inside `extra_body` raises `ValueError`
before the hook; the host does not silently strip them. Agent execution controls can reach the hook for filtering,
but cannot be returned. Hook results also cannot contain host controls,
`extra_body`, or execution controls such as `client_kwargs`, `middleware`, `session`, and tool-invocation kwargs.
Responses native `instructions` and `tools` remain supported; Invocations agent options additionally reject both.
Developer defaults cannot use nested transport controls to bypass storage or background policy.
For a custom agent that cannot accept MAF runtime options, choose
`unsupported_options` as `"ignore"`, `"warn"` (default), or `"error"`. See the
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

### Invocation-time OAuth consent

With `history_source="host_managed"` or `"agent_managed"` and `store=true`, a Foundry Toolbox MCP `tools/call`
that requires OAuth consent produces a structured continuation rather than an opaque error.
The Responses agent response has status `incomplete`, and its output contains:

- the `function_call` for the protected tool;
- a `function_call_output` for that call, whose text says that OAuth consent is required;
- an `oauth_consent_request` item with `consent_link` and `server_label`.

The host emits a consent request for one `(consent_link, server_label)` pair only once in a response. Non-streaming
calls return these items in the final response. Streaming calls give the same items. The host buffers them and
publishes them only after it saves the session snapshots.

Other tool calls in the same run behave as follows:

- Tool calls that completed before the consent error keep their real results.
- The host does not run later protected Toolbox calls in the same run. Each one gets a
  "not executed because another tool requires OAuth consent" output.
- Each `function_call` gets exactly one terminal output.

To continue, the user opens `consent_link` and gives consent. The client then sends a new request with
`previous_response_id`, and the agent tries the tool again.

Failure boundaries:

- The response fails if a consent link is not a safe absolute HTTPS URL or is outside the configured origin
  allowlist. The host does not expose that URL.
- Consent continuation requires `store=true`. If the request has `store=false`, the response fails and the host
  exposes no consent or approval output. Consent appears during tool execution, after the response has started, so
  this is a failed response, not an HTTP 400 rejection.
- Invocation-time consent is unsupported with `history_source="inference_service"`: the response fails explicitly
  rather than publishing a continuation that the service-owned history cannot safely resume.
- Consent at connection time (`tools/list`) behaves as before.

Limits:

- The host does not cancel sibling tool calls that are already running.
- Only Toolbox tools are blocked. Other tools continue to run.
- The host must activate the request scope, so this behavior needs the hosted runtime.
- Core can log the consent exception.

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

## Responses citation annotations

`ResponsesHostServer` serializes supported framework URL and file citations into `output_text.annotations`.
URL and container-file citation spans refer to character positions in the generated response text.
Annotations with `annotated_regions_coordinate_space == "source"` retain source-document coordinates
(for example, Anthropic character, page, or block locations); the host does not emit those regions as
output-text spans. Other supported citation metadata, such as file citations with an explicit output index,
is still converted.
Completed provider responses retain separate text content parts, keeping citation offsets relative to
their original part. Ordinary streaming deltas still merge within their existing text occurrence,
without shifting citation offsets.

## State store

### Local persistence

Outside the Foundry hosting environment, state is persisted as JSON files under
`~/.agentserver/state_stores` by default. Set `AGENTSERVER_STATE_ROOT` to use a
different root directory; the files will be written to its `state_stores`
subdirectory instead.

Each logical store is saved as one JSON file whose name is a URL-safe Base64
encoding of the store name. For example:

- Responses agent sessions: `YWdlbnRfc2Vzc2lvbnM.json`
- Workflow checkpoints: one file per context, encoded from `checkpoints/<context_id>`

The file-based fallback supports ordinary session and checkpoint persistence, including pending agent
approvals. It coordinates writers within one process only.

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

The default hosted MAF session and checkpoint stores use a `v2` namespace
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
separate mutable conversation-head key is also updated. Loaded MAF sessions use that key's loaded revision:
a competing turn that advanced the head causes a visible conflict rather than a stale overwrite. In
`"inference_service"` or `"agent_managed"` history mode, a
stored named-conversation turn first claims that head with a conditional write *before* calling the inner agent.
Another request that read the old head loses the CAS; one that reads the claim fails before touching the provider.
The claim is cleared when the winning turn successfully commits the new head. If a dispatched turn fails or is
cancelled, the claim remains: the provider may already have changed its thread, so start a new conversation
instead of retrying this one blindly. A recovered provider-background turn must still own the same claim.
The committed head also records its completing outer response ID. If a crash occurs after the head write but before
outer completion, that response can recover its saved final output without reclaiming or rewriting the head.
A different in-flight claim or completing response is not accepted as ownership.
When continuing by `previous_response_id`, the prior response is claimed with a conditional write **after**
the input is validated, so invalid input does not consume a usable parent. A second branch
cannot reuse the same downstream service thread; attempting to fork a named service conversation is also rejected.
New hosted keys are created only if absent. Custom store providers must provide equivalent scoped conditional
writes for concurrent turns, including the pre-dispatch claim. Local callers can still upsert directly without
first loading a session.

See the [custom storage provider sample](../../samples/04-hosting/foundry-hosted-agents/responses/custom_storage/)
for an example that uses an in-memory session store locally and a user-managed Azure Cosmos DB account when hosted.
Its Cosmos prerequisites apply to that custom provider, not to the default Foundry-managed store.

Native Responses refusal parts are stored as text carrying
`additional_properties["model_output_kind"] == "refusal"` and emitted as
`response.refusal.*` events when streamed back to clients.

`InvocationsHostServer` restores sessions from its configured store. When hosted, `AgentSession.session_id` is an
opaque composite identifier that preserves the boundaries between the platform session ID
and user ID. Consumers must use it as a whole and must not parse it or depend on its internal
representation. Repeated requests for the same identifier pair restore the saved session.
Locally, the platform session ID is used unchanged.

### Invocations agent requests and response format

By default, `POST /invocations` accepts `{"message": "Hi", "options": {}, "stream": false}`. Applications can supply
a sync or async `parse_input(request)` returning a typed `InvocationRun(messages, options, stream)` to accept their
own JSON shape and MAF `Message` inputs. A sync or async `prepare_options(request, options)` hook can filter or replace
a **copy** of this turn's caller options without changing the agent's `default_options`. It must return a mapping
with string keys; only the returned, validated options are forwarded. Without a hook, caller model-run options
are suppressed and developer defaults apply. The host rejects reserved platform/session fields, `store`,
`extra_body`, and private continuation fields after the hook; callers cannot select another sandbox or enable downstream service continuation through
runtime options. It also rejects agent execution controls: `additional_function_arguments`, `function_invocation_kwargs`,
`client_kwargs`, `middleware`, `session`, `tools`, `instructions`, `compaction_strategy`, and `tokenizer`. Trusted tool
arguments belong in developer-configured agent defaults or middleware/factories, not in request options or hook output.
A hook may strip denied caller fields before validation; allowed generation and provider-specific options remain
available. These restrictions apply to streaming and non-streaming requests under every `unsupported_options` policy.
When an agent cannot accept runtime options, `unsupported_options="warn"` (default) logs and ignores
them; `"ignore"` silently drops them and `"error"` rejects them. For request-scoped factories, unsupported options
discovered after streaming starts are reported as an SSE `error` event with `status: 400`.

Non-streaming success is JSON `{"response": "..."}`. Streaming success is framed SSE
`event: delta` with `{"text": "..."}`, followed by `event: done` with the platform sandbox `session_id`.
The `done` event is sent only after the final MAF `ResponseStream` is finalized and the session is persisted.
Client validation errors return JSON HTTP 400 before streaming where possible. Provider errors are logged and
sanitized as JSON HTTP 500 or an SSE `error`; a cross-process ETag conflict is JSON HTTP 409 or an SSE `error`
with `code: "session_conflict"` and `status: 409`. A stream may emit deltas before an error. The host serializes
same-session requests in one process, but a CAS conflict can still follow external tool effects in separate
processes; it does not guarantee exactly-once execution. See the
[Invocations agent/parser example](../../samples/04-hosting/foundry-hosted-agents/invocations/basic/).

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

`ResponsesWorkflowHostServer` and `InvocationsWorkflowHostServer` persist native workflow checkpoints.
By default, they use the `FoundryCheckpointStore`, backed by Foundry storage when hosted and file-based storage
locally. Stored checkpoints are scoped under `checkpoints`.

### Function approvals

`ResponsesHostServer` uses the framework's built-in approval handling. Core records each pending
`function_approval_request` in the `AgentSession`, and the host saves that session with the configured
`agent_session_store_provider`. When a reply arrives, the host loads the same session and translates each
`mcp_approval_response` to a `function_approval_response`. Core binds the reply to its recorded request,
rebuilds the call from that request, and consumes it. A reply that matches no pending request is not executed.

The SDK generates the wire ID of each `mcp_approval_request` item. The host keeps a map from that wire ID to
the original request in the same session state. The map only translates IDs; it does not authorize execution.
Custom session stores need only the ordinary `SessionStore` operations.

- Approvals and rejections may be mixed in one reply.
- A partial reply is allowed. Core holds the batch until every request has a reply, and the response emits the
  unanswered requests again under new wire IDs. Reply to those new IDs.
- The host drops a reply with an unknown wire ID and logs a warning. A turn whose input contains only dropped
  replies fails.
- Invalid replies are not rejected before the response starts. They produce a failed response instead of an
  HTTP 400.
- `store=false` cannot persist or resume pending approvals.
- Concurrent replies, forks, and retries have the same guarantees as any agent run that shares a session.
  Approval handling does not provide exactly-once tool side effects.

Native workflows keep pending replies in their `request_info` requests and checkpoint, not in an agent session.
`ResponsesWorkflowHostServer` maps wire IDs to request IDs in the checkpoint binding. A partial reply runs the
answered requests, and the response emits the unanswered requests again under new wire IDs. A reply that the
workflow runtime rejects before its first superstep, such as an unknown request ID or a mismatched reply type,
fails the turn and leaves the lineage head unchanged, so a valid reply can be retried. A failure after a
superstep starts blocks that lineage.

**Migration/reset:** pending approvals from the old separate function-approval store are not
migrated. Start a fresh conversation without an old `previous_response_id` or conversation ID and
obtain fresh approvals. Do not copy legacy approval records into session state.
The public `FunctionApprovalStore`, `FoundryFunctionApprovalStore`, and `FunctionApprovalStoreProvider`
exports and the `function_approval_store_provider=` constructor setting are removed.

## Native Invocations workflows

Host a native workflow with an explicit application parser rather than wrapping it
with `workflow.as_agent()`, which agent hosts reject (see
[Migrate `WorkflowAgent` hosting](#migrate-workflowagent-hosting)):

```python
from agent_framework_foundry_hosting import CheckpointStoreProvider, InvocationsWorkflowHostServer

server = InvocationsWorkflowHostServer(
    workflow=build_workflow,
    parse_input=parse_input,
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
clients, providers and mutable tools for each request. Allocation must not execute
tools or workflow side effects. Both hosted and local workflows require a factory; built instances
are rejected at construction. Successfully entered factory-agent contexts are
unwound per turn; see [factory resource lifecycle](#factory-resource-lifecycle)
for the pre-entry and client-ownership limits. Applications must explicitly own
external credentials and providers through their resource-managing agent
subclasses. Do not configure another checkpoint store on `WorkflowBuilder` or
share mutable graphs between requests.

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
cross-scope and replayed replies fail before executor/response-handler dispatch.
A partial reply runs the answered requests; the rest stay pending under their
request IDs. Unallowlisted batches are rejected before the turn is claimed. A
reply that the workflow runtime rejects before its first superstep fails the turn
and leaves the head unchanged, so a valid reply can be retried. Native factories
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
interruption cannot emit successful completion. Turns that fail after their first
superstep starts are blocked to avoid replaying uncertain effects; start a new sandbox instead of blindly
retrying non-idempotent work. Checkpoints do not provide exactly-once tool effects.
If a connection drops after commit, retrying the same trusted user/sandbox/call ID
replays that response's complete stored snapshot without executing the workflow or
replacing its head. A different call ID starts normal turn validation and cannot
retrieve that snapshot.
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
contract. Agent-only `prepare_options` and
`agent_session_store_provider` are rejected for native workflows rather than
silently reinterpreted.

See the [typed Ticket/review example](../../samples/04-hosting/foundry-hosted-agents/invocations/basic/README.md#native-workflow-with-typed-tickets)
for the parser, stable graph, checkpoint type allowlist, pending replies,
JSON/SSE and local/hosted migration guidance.
