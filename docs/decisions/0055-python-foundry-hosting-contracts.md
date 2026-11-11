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
workflow parsers return `WorkflowTurn` containing either typed start input or complete pending replies.
Parsing does not replace the host's checkpoint and pending-authority validation.
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

Native workflow factories are request-aware and must allocate fresh workflows, executors, agents,
clients, providers, and mutable tools. A new graph wrapper around shared executors is not isolation.
Reject known shared execution resources rather than cloning them. This guard cannot prove that arbitrary
application globals are isolated. Keep workflow names and executor IDs stable for checkpoint restoration.

Close factory-owned context-managed agents for the request, including failure and cancellation cleanup.
Applications own cleanup of other resources they create; caller-owned shared resources must not be closed.
State needed across requests belongs in supported stores, not request-owned instance fields.

### Persistence and history ownership

Regular agents continue through agent-session storage. Native workflows continue through their exact
scoped checkpoints, including pending-reply authority. Neither execution model converts the other's state.
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
Reject hidden provider background under an outer foreground request.

Outer workflow background must not enable background on constituent agents. Native inner provider
background is unsupported. Do not introduce a per-agent workflow-host background switch.
Recovery permission neither selects an execution mode nor guarantees exactly-once external side effects.

Allow top-level `background` values of `False` or `None`, and reject nested `extra_body.background` in
every mode. Validate caller options, hook results, and developer defaults before execution. Also check the
effective options and client kwargs from ordinary agent middleware and client-level chat middleware before
the provider call. For a native `RawAgent`, install the check after existing client middleware on the fresh
client that the host owns. Make native `WorkflowTurn` reject client-level and run-level middleware. Report
middleware violations as execution failures, not as client input errors.

Do not claim universal interception and do not change Core for this check. Core can append chat middleware
from context providers after the guard, so applications must not enable provider background there. Clients
that internally force provider background are unsupported.

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

Use session-backed authority for regular-agent approvals rather than a separate public approval-store API.
Native workflow pending authority remains checkpoint-owned. Keep one canonical pending batch in the configured
session store; response and conversation aliases retain history and a link, not independent permission.
Require structural `get_with_revision` and `compare_and_set` methods with create-only and exact-revision
semantics. Foundry-managed storage uses AgentServer's create-only and conditional-write primitives without
assumptions about its underlying topology. Custom providers must coordinate all writers; a process-local
lock does not provide cross-process approval authority. Old separate-store approvals require a fresh
conversation, not a silent migration.

Reject incomplete hosted MCP approval sets with HTTP 400 before streaming, response headers,
`response.created`, or protected dispatch, without consuming pending authority.
A complete batch may mix approvals and rejections.
Revalidate and claim authority after other reservations and before protected dispatch. A race after preflight
can still fail after streaming starts. A consumed or uncertain claim is not reopened automatically, including
when the client repeats the same response ID. Non-approval redelivery retains the SDK's behavior.
No claim provides exactly-once external side effects.

Represent invocation-time OAuth consent as structured consent with incomplete response status.
Pair each emitted function call with one terminal result, preserve completed sibling results, and stop
later protected calls. Require `store=true` so continuation can retain the required state;
do not support ephemeral consent under `store=false`.
Buffer authority-bearing output until authority and snapshots are saved. Invocation-time consent with
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
invocation, failure/cancellation cleanup, and rejection of shared workflow resources.
Exercise streaming and non-streaming execution, session/checkpoint continuation, pending replies,
and model-free process crash/recovery. Validate maintained samples against public exports.
Offline checks do not establish live Foundry deployment compatibility.
