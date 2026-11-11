---
status: proposed
date: 2026-11-10
deciders: ["@eavanvalkenburg"]
---

# Python Foundry hosting contracts

## Context and Problem Statement

Foundry agent and native workflow hosting have different construction and state-ownership contracts.
A combined constructor exposes settings that apply to only one execution model and makes required
workflow inputs appear optional. Hosting also spans several distinct concerns: caller-visible
persistence, agent history, workflow checkpoints, downstream inference storage, background execution,
and recovery.

The public API must make these boundaries explicit without duplicating protocol engines or implying
stronger persistence and execution guarantees than the underlying systems provide.

## Decision Drivers

- Make required inputs and state ownership visible in public signatures.
- Resolve identity-dependent resources from trusted request context.
- Isolate workflow execution state without cloning graphs or redesigning Core.
- Use consistent terminology while preserving protocol-specific request contracts.
- Expose supported configuration rather than the upstream SDK's entire options surface.

## Considered Options

- Separate agent and workflow hosts: explicit contracts, at the cost of more public entry points.
- One host with typed configuration groups: fewer entry points, but extra configuration layers.
- One flat constructor: fewer types, but conditional requirements and invalid setting combinations.

## Decision Outcome

Choose separate agent and native workflow hosts. Share protocol internals, but keep construction,
configuration, and state ownership specific to each execution model.

The decisions below define the intended hosting contracts, not the implementation status of each feature.
See the [Foundry Hosting README](../../python/packages/foundry_hosting/README.md) for the current usage contract.

### Host boundaries

Use `ResponsesHostServer` and `InvocationsHostServer` for agents, and
`ResponsesWorkflowHostServer` and `InvocationsWorkflowHostServer` for native workflows.
Agent hosts reject `WorkflowAgent`; workflow hosts require a factory returning a native `Workflow`.
Do not silently unwrap agents, migrate their state, or retain a combined-host compatibility shim.

Workflow hosts expose checkpoint storage rather than agent-session storage or agent history settings.
The Responses workflow host owns native execution directly. Share the Invocations engine between its
public hosts rather than duplicating it. Group each protocol into agent, workflow, and shared modules,
with cross-protocol request contracts and factory resolution in a central shared module.

Keep all hosts in one package. Responses is the initial stable-surface target; Invocations and Toolbox
remain experimental. Separate classes do not require separate distribution packages.

### Request adaptation and construction

Use `parse_input` for custom input adaptation across both protocols. Agent parsers return `InvocationRun`;
workflow parsers return `WorkflowTurn` containing either typed start input or pending replies.
Parsing does not replace the host's checkpoint binding or the workflow runtime's reply validation.
Use `ResponsesRequest` for the Responses wrapper, including factory and option-hook inputs.
Do not retain aliases for the former parser keywords or request-type name.

Agent hosts accept an instance or a sync/async factory implementing a named-request callable protocol.
Factories must declare a required `request` parameter and are called as `factory(request=request)`.
Additional parameters may have defaults; the factory may ignore the request. Reject zero-argument,
positional-only request, and implicit `**kwargs`-only factories rather than guessing which parameter
represents request context. Validate the signature before invocation. Never retry a factory-body
exception with a different call shape: that could duplicate side effects.

Responses agent factories receive trusted scope, current-turn input, and translated caller options
before `prepare_options`. Invocations agent factories receive the Starlette `Request` after parsing
and option preparation. Preserve these protocol-specific timings rather than forcing identical signatures
or inventing a shared options-precedence policy.

Caller model-run options are opt-in for Responses agents, Responses workflows, and Invocations agents.
Without `prepare_options`, do not forward caller generation settings; preserve developer defaults and
host-owned storage/background controls. With a hook, forward only its returned, validated mapping.
This does not prevent application code from inspecting the original request. Responses agent factories
see translated options before the hook. Native Responses workflow factories run after the hook and
see its selected options, or an empty option mapping when no hook is configured.

Native workflow factories are request-aware and must allocate fresh workflows, executors, agents,
clients, providers, and mutable tools. A new graph wrapper around shared executors is not isolation.
Reject known shared execution resources rather than cloning them. This guard cannot prove that arbitrary
application globals are isolated. Keep workflow names and executor IDs stable for checkpoint restoration.

Unwind successfully entered factory-agent contexts when a request finishes, fails, or is cancelled.
`Agent` also unwinds client and MCP contexts already entered if a later context fails to enter.
Allocations before agent entry and partial allocations from a failed client `__aenter__` may not be
cleaned up; calling `agent.close()` before entry does not dispose an unentered client.
Applications own cleanup of other resources they create. An entered caller-supplied context-managed
client can be closed on agent exit; ownership depends on its context contract, and the host cannot
reliably identify shared clients on first use. State needed across requests belongs in supported stores,
not request-owned instance fields.

### Persistence and history ownership

Regular agents continue through agent-session storage. Native workflows continue through their exact
scoped checkpoints, including pending `request_info` requests. Neither execution model converts the other's state.
Native workflow agents use checkpoint-owned history, not private inference-service continuation.

Keep three storage decisions distinct:

- The wire-level `store` flag controls caller-facing Responses persistence.
- The constructor's `response_store` selects the backend for that persistence.
- `history_source` selects who supplies prior messages to the model.

Use `history_source="host_managed"` by default, with `"agent_managed"` and `"inference_service"`
as explicit alternatives. `agent_managed` permits developer-owned history providers or downstream
service storage; it is not restricted to `HistoryProvider`. Remove the constructor `store=` alias,
including acceptance of `None`, without changing the wire flag or downstream storage controls.

### Background execution and recovery

Treat outer background execution, inner inference-service background execution, and recovery permission
as separate controls. Use `background_source="host_managed"` by default. Retain `"inference_service"`
for supported regular agents with inference-service history and outer-background passthrough.
Validate hosting-visible agent and factory defaults against the selected background mode.

Outer workflow background must not enable background on constituent agents. Native inner provider
background is unsupported. Do not introduce a per-agent workflow-host background switch.
Recovery permission neither selects an execution mode nor guarantees exactly-once external side effects.

For regular Responses and Invocations agents, allow an application options hook to select `background`;
the application owns that choice. Ordinary Responses agent runs preserve hook-selected values. When the host
explicitly selects provider background, retain `background=True` for submission and polling even if the hook
returns `False`. Hook-selected background alone does not enable host-managed polling or recovery. Invocations
does not inject an outer background value.

Do not inject background-specific enforcement middleware or add a Core interception hook. Application agent/chat
middleware owns its changes to background options. Keep validation of caller envelope fields, hook results
other than the agent hook's background choice, and developer defaults before execution. Reject nested caller
`extra_body.background` before the Responses hook. Native workflow option hooks cannot select inner provider
background; make native `WorkflowTurn` reject client-level and run-level middleware. The existing native agent
options middleware still validates transport controls, storage, and unfinished provider responses to preserve
checkpoint ownership; it is not the removed background-specific guard.

### Supported host settings

Expose supported first-class settings and construct SDK options internally, without another framework
options wrapper. Reject inapplicable or removed settings before side effects; do not leak them through
`**kwargs` to the SDK.

| Setting | Contract |
| --- | --- |
| `max_history_items: int \| None = None` | `None` supplies no framework override and inherits the installed supported SDK's default. Positive caps count prior history items and apply only to regular host-managed agent history. |
| `sse_keep_alive_interval_seconds: int \| None = None` | Use an explicit positive interval, otherwise inherit a positive `SSE_KEEPALIVE_INTERVAL`, otherwise disable heartbeats. No separate force-disable switch. |
| `shutdown_grace_period_seconds: int = 10` | Shutdown waiting, not a per-request timeout. Also document the upstream reuse for DELETE waiting on response persistence. |
| `enable_background_recovery: bool = False` | Permit recovery of eligible background work without selecting background execution. |

Do not interpret a history limit of `None` as unlimited, map it to `-1`, or raise the dependency floor
to obtain a particular SDK default. History caps do not limit tokens, turns, retention, or checkpoints.
Heartbeats are not model or request timeouts.

Configure inference defaults on agents and clients, not through host `default_model`. Do not expose
host span callbacks, server-version stamping, or steering settings. Retain framework observability
and keep steering disabled. Removing host defaults does not redefine caller-supplied request models
or other request-option precedence.

### Approvals and consent

Use the framework's built-in approval handling and do not add a host approval authority.
Regular agents keep pending approval requests in the same `AgentSession` that the host loads and saves through
the configured session store. Core binds each approval response to a recorded pending request, rebuilds the call
from that request, and consumes it. The host stores only a translation map from the SDK-generated wire item ID to
the original request in that session's state. This map does not authorize execution. Native workflows use
`request_info` and their exact checkpoint; the host translates wire IDs to request IDs in its checkpoint binding.
There is no separate public approval-store API, no conditional-write capability for custom session stores, and no
silent migration of old separate-store approvals.

Do not preflight approval replies before the response starts. The host drops a reply with an unknown wire ID
with a warning, and the framework does not execute a reply that matches no pending request. A turn whose input
contains only dropped replies fails. Partial batches follow the framework: an agent holds the batch until every
request has a reply, and a workflow runs the answered requests. Responses hosts emit requests that are still
pending again under new wire IDs; Invocations workflows keep their request IDs. A batch may mix approvals and rejections. A workflow reply that the runtime rejects before its first superstep releases the
lineage head unchanged; a failure after a superstep starts blocks that lineage. Concurrent replies, forks, and
retries have the same guarantees as any agent run with a shared session or any workflow checkpoint resume.
No path provides exactly-once external side effects.

Represent invocation-time OAuth consent as structured consent with incomplete response status.
Pair each emitted function call with one terminal result, preserve completed sibling results, and stop
later protected calls. Require `store=true` so continuation can retain the required state;
do not support ephemeral consent under `store=false`.
Buffer consent and approval output until the session snapshots are saved. Invocation-time consent with
inference-service history is unsupported and fails explicitly; connection-time consent remains separate.
A consent failure after execution starts is a failed response, not a pre-header HTTP 400.

### Caller options

Preserve protocol-specific option ordering. Responses translates generation fields before factory resolution
and its hook; Invocations parses and applies its hook before factory resolution. Deep-copy per-run hook input
and replacement mappings without changing developer defaults. Protect hosting and execution controls after
the hook, and reject those controls inside nested transport options. The host split does not authorize
removing existing hooks or applying workflow-only assumptions to regular agents.

### Unresolved boundaries

Do not infer a single-target restriction or a multi-target router without a documented Foundry platform
contract. Request `model` is not implicitly an agent selector.

Keep current dependency requirements and the steering guard until published-wheel compatibility and
concurrent queue-overflow behavior are verified. An upstream merge alone is not release evidence.
These decisions do not redesign Core, concurrency, checkpoints, retries, or external exactly-once execution.

## Consequences

- Public signatures identify execution models and their state owners.
- Shared internals avoid duplicate engines without obscuring public contracts.
- Request-aware factories support identity-dependent resources but require deliberate isolation and cleanup.
- The API migration breaks combined-host construction, wrapper hosting, unnamed or zero-argument agent factories, old parser/request names, source literals, and the storage-backend alias.
- Settings, authority, and consent changes require their own implementation and correctness validation; recording a decision does not establish that it has shipped.

## Validation

Cover public imports and signatures, invalid construction before SDK side effects, sync/async factory
invocation, cleanup of successfully entered contexts on failure/cancellation, and rejection of shared
workflow resources.
Exercise streaming and non-streaming execution, session/checkpoint continuation, pending replies,
and model-free process crash/recovery. Validate maintained samples against public exports.
Offline checks do not establish live Foundry deployment compatibility.
