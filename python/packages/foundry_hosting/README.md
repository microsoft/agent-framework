# Foundry Hosting

This package provides the integration of Agent Framework agents and workflows with the Foundry Agent Server, which can be hosted on Foundry infrastructure.

Implementation is grouped by protocol: `_responses_agent.py` and `_responses_workflow.py` define the Responses hosts,
and `_responses_shared.py` contains their wire and streaming helpers. Invocations uses the same `_invocations_agent.py`,
`_invocations_workflow.py`, and `_invocations_shared.py` layout. Cross-protocol request contracts, option validation,
and agent/workflow factories live in `_shared.py`. Applications use the public package imports below.
Both Invocations hosts inherit directly from the SDK host; shared functions handle identity, wire conversion,
and streaming cleanup without a combined agent/workflow host.

## Choose the host

Use `ResponsesHostServer` or `InvocationsHostServer` for agents. Use
`ResponsesWorkflowHostServer` or `InvocationsWorkflowHostServer` for native workflows.
Each workflow host requires a request-aware sync/async factory and an explicit parser.
All four hosts remain in `agent-framework-foundry-hosting`, with matching lazy exports
under `agent_framework.foundry`. Invocations and Toolbox retain their experimental boundary;
the split does not promote them.

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
explicit workflow kwargs instead. Regular-agent approval state belongs to the native
agent and its `AgentSession`; no separate approval-store API is exposed.
Agent hosts reject `WorkflowAgent`, whether supplied directly or returned by a factory.
`checkpoint_store_provider` is available only on workflow hosts.
No stored state is converted between native workflow and agent execution models.

## Explicit host configuration

Responses hosts construct the upstream
[`ResponsesServerOptions`](https://pypi.org/project/azure-ai-agentserver-responses/) internally.
Use first-class host parameters rather than importing an SDK options bag:

| Parameter | Available on | Meaning and SDK consumer |
| --- | --- | --- |
| `log_level=None` | All four hosts | A literal `"DEBUG"`, `"INFO"`, `"WARNING"`, `"ERROR"`, or `"CRITICAL"`, forwarded unchanged to the AgentServer SDK constructor. `None` preserves the SDK default. |
| `max_history_items: int \| None = None` | Responses agent host, with `history_source="host_managed"` | A positive cap on prior outer history items, passed to the SDK history loader as `default_fetch_history_count`. `None` supplies no override and inherits the installed supported SDK's default. |
| `sse_keep_alive_interval_seconds: int \| None = None` | All four hosts with framed SSE | A positive streaming heartbeat interval in seconds. Responses forwards it to SDK streaming routes; Invocations sets the host's SDK heartbeat configuration. `None` inherits a positive `SSE_KEEPALIVE_INTERVAL`, otherwise heartbeats are disabled. |
| `shutdown_grace_period_seconds: int = 10` | Both Responses hosts | A positive shutdown wait in seconds. The SDK also uses it when DELETE waits for response persistence. It is not a request or inference timeout. |
| `resilient_background: bool = False` | Both Responses hosts | Uses the SDK's recovery setting without renaming it. It permits eligible recovery, not background execution or exactly-once side effects. |

`max_history_items=None` does **not** promise unlimited history or map to SDK `-1`.
Supported SDK versions can have different defaults. Explicit caps count prior history items, not tokens,
turns, retention, or workflow checkpoints. Other agent history modes and workflow hosts do not accept a cap.

Explicit heartbeat intervals must be positive: zero, negative values, and booleans are invalid, not
force-disable switches or requests to inherit the environment. The SDK still parses its environment
configuration during construction; a malformed `SSE_KEEPALIVE_INTERVAL` can fail even with an explicit interval.
The agent-only `legacy_wire_format=True` disables heartbeats and cannot be combined with an explicit interval.

For regular-agent recovery, select both `history_source="inference_service"` and
`background_source="inference_service"`. Native workflows recover from their own checkpoints.
The SDK recovery setting itself is provider-independent; the inference-service requirement is a limitation
of the regular-agent adapter, which currently resumes only saved provider continuations.
Follow the SDK's task-subsystem and persistent-store requirements. Neither outer workflow background execution nor
recovery permission enables provider background on constituent agents.

Host `default_model`, `create_span_hook`, `additional_server_version`, and `steerable_conversations`
are not first-class parameters. Framework-generated SDK options leave model defaults, span callbacks, and
custom version stamping unset, and keep steering disabled. Framework observability is unchanged.
Configure inference defaults on the agent or client. The former SDK `default_model` could fill the outer
request model and thereby override inference; it did not select a hosted agent. Removing that host fallback
does not change caller-supplied request models, option-hook timing, option precedence, or routing.

### SDK constructor arguments

All four hosts accept `agent_server_kwargs: Mapping[str, Any] | None = None`.
This caller-owned mapping is expanded only into the corresponding AgentServer SDK constructor.
Hosting does not inspect, validate, filter, or mutate its contents. Python and the SDK report invalid
arguments, including collisions with arguments the framework already supplies; there is no custom merge policy.
An SDK argument reaching this boundary does not mean every adapter path supports its behavior.

Move SDK-specific top-level arguments into this mapping. For an application-owned `agent` and `asyncapi_spec`:

```python
from agent_framework_foundry_hosting import InvocationsHostServer

# Before: InvocationsHostServer(agent=agent, asyncapi_spec_json=asyncapi_spec)
server = InvocationsHostServer(
    agent=agent,
    agent_server_kwargs={"asyncapi_spec_json": asyncapi_spec},
)
```

The constructors no longer accept arbitrary `**kwargs`. Removed top-level names, including `options=`
and old parser/storage aliases, raise Python `TypeError` before construction, even when their value is `None`.
Use the first-class parameters above for framework-supported configuration. Runtime model options,
`client_kwargs`, and `function_invocation_kwargs` keep their existing meanings and validation.

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

Construct tool objects inside the workflow factory as the default. A module-level
`@tool` decorator constructs one shared `FunctionTool`, including its invocation
counters and configured lifetime limits. The current ownership guard rejects
reusing that object across native workflow requests, even if its function is pure.

A plain Python function can be defined outside the factory and wrapped with
`tool(function)` inside it to create a fresh tool object for each workflow.
This does not copy state captured by the function, bound objects, wrapped agents,
or connections. Developers must manage that state and its isolation explicitly;
moving only the wrapper construction does not make shared mutable resources safe.

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

With `resilient_background=True`, native workflows recover through the
AgentServer resilient task subsystem; SDK-specific task initialization and persistence requirements still apply.
Host-owned checkpoint/output pairs
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

The existing `history_source="agent_managed"` still preserves the agent's own provider **or** service storage defaults
on stored requests, including `default_options={"store": True}`. Custom `SupportsAgentRun`
implementations can continue using that mode for stored requests; it is not a forced-provider mode.
The outer storage-backend constructor argument is `response_store=`. The old `store=` backend
argument is rejected, including `None` and calls that also supply `response_store=`.
The backend selector does not set the caller's per-request `store` flag.

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
Use `resilient_background=True` to permit recovery from a **saved** token; a crash before
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
Regular agent runs without this opt-in are not crash-replayable. **Steering is unavailable:**
`steerable_conversations` and the upstream `options` bag are not host parameters; framework-generated SDK
options keep steering disabled.
The current AgentServer SDK retains unbounded futures for rejected turns when its steering queue fills. Do not
use a queue-length precheck: another worker can append before it. Future steering support requires an
official `azure-ai-agentserver-core` wheel containing
[Azure/azure-sdk-for-python#49233](https://github.com/Azure/azure-sdk-for-python/pull/49233), updated minimum
dependencies and `uv.lock`, and a concurrent queue-overflow regression proving rejected turns leave no pending futures. No future SDK
version is assumed. Non-steerable agent background polling is unchanged.

Native CreateResponse generation fields become MAF runtime options (notably `max_output_tokens` -> `max_tokens` and
`parallel_tool_calls` -> `allow_multiple_tool_calls`). Flattened OpenAI `extra_body` fields overlay translated keys
**last**. A sync or async `prepare_options(request: ResponsesRequest, options: dict)` hook can remove or replace
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
separate mutable conversation-head key is also updated. Loaded MAF sessions use PR1's ETag condition for that key:
a competing turn that advanced the head causes a visible conflict rather than a stale overwrite. A superseded
steered turn saves its response snapshot but skips the head update. In `"inference_service"` or `"agent_managed"` history mode, a
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
a sync or async `parse_input(request)` returning a typed `InvocationRun(messages, options, stream)` to accept their
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

`ResponsesWorkflowHostServer` and `InvocationsWorkflowHostServer` persist native workflow checkpoints.
By default, they use the `FoundryCheckpointStore`, backed by Foundry storage when hosted and file-based storage
locally. Stored checkpoints are scoped under `checkpoints`.

### Function approvals

The native agent tracks pending approvals, validates decisions, and consumes them
in its `AgentSession`. Hosting persists and restores the complete native session
through `agent_session_store_provider`; it does not maintain a second approval store.
An approval reply must continue the issuing session through `previous_response_id`
or a named conversation. The wire approval ID alone does not establish authority.

Custom agents must establish matching native pending state by the end of a run
that emits an approval request. Hosting rejects unmatched or unrecorded requests
before publishing an approval item; it does not register approvals on an agent's behalf.

AgentServer requires its own wire-ID format. The adapter stores only native-ID
and session-ID correlation in the response item's internal metadata, which the SDK
removes from client-facing responses. It resolves that metadata through the scoped
response provider, independently of model-history limits, then delegates binding
and consumption to Core. Native workflow authority remains in its exact checkpoint.

Remove `function_approval_store_provider` and imports of `FunctionApprovalStore`,
`FoundryFunctionApprovalStore`, and `FunctionApprovalStoreProvider` when upgrading.
Old approval-store records are not migrated. Start a fresh conversation rather
than resuming approvals emitted before this migration.

Approval output waits for native finalization, and the session is saved before
an approval request is published. This preserves Core's existing session-level
guarantees, not durable single-consumption across
concurrent workers or independently restored old snapshots. Stronger session-store
coordination is separate work. Incomplete hosted MCP batches still need the SDK
preflight support tracked by #9537 to return HTTP 400 before streaming starts;
this migration does not claim that behavior.

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
clients, providers and tools for each request; allocation must not execute tools or
workflow side effects. Both hosted and local workflows require a factory; built instances
are rejected at construction. Factory-owned agents are entered and
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
Local callers also use a request-aware factory, including one-shot non-pausing
runs. Each request receives a fresh graph; a continuation restores and consumes
its durable reply from the exact scoped checkpoint.
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
