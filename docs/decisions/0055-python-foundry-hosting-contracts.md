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
Both Invocations hosts inherit directly from the SDK host and own their mode-specific construction,
parsing, state, and execution. Do not retain a private combined host or replace it with a mode-switching
base or mixin. Share small identity, wire, and streaming-cleanup helpers rather than duplicating protocol
logic. Group each protocol into agent, workflow, and shared modules,
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

Construct tool objects inside the workflow factory as the default. Module-level `@tool` decoration
constructs one shared wrapper with its own lifetime counters and any captured resources. The current
ownership guard rejects reused function-tool objects without attempting to infer function purity.
A function may be defined elsewhere and wrapped inside the factory, but developers remain responsible
for captured or externally shared state. Fresh wrappers do not clone that state or establish isolation.

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

### Supported host settings

Expose supported first-class settings and construct SDK options internally, without another framework
options wrapper. Validate framework-owned settings and their applicability before side effects.
Remove variadic constructor `**kwargs` from all four public hosts. Unknown top-level names fail through
Python argument binding, including removed names supplied as `None`.

Expose `agent_server_kwargs: Mapping[str, Any] | None = None` as a separate, caller-owned SDK boundary.
Expand its entries only into the upstream SDK constructor, without inspecting, validating, filtering,
or mutating the contents. Let Python and the SDK report invalid arguments and duplicate keyword
collisions; do not add a reserved-key blacklist or a custom merge policy. This does not remove validation
of framework parameters, caller model options, hooks, or execution policies.

| Setting | Contract |
| --- | --- |
| `log_level=None` | Available on all four hosts as `Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] \| None`, forwarded unchanged to the SDK constructor. `None` preserves the SDK default. |
| `max_history_items: int \| None = None` | `None` supplies no framework override and inherits the installed supported SDK's default. Positive caps count prior history items and apply only to regular host-managed agent history. |
| `sse_keep_alive_interval_seconds: int \| None = None` | Available on all four framed-SSE hosts. Explicit values must be positive; zero and negative values are invalid. `None` inherits a positive `SSE_KEEPALIVE_INTERVAL`, otherwise disables heartbeats. No separate force-disable switch. |
| `shutdown_grace_period_seconds: int = 10` | Shutdown waiting, not a per-request timeout. Also document the upstream reuse for DELETE waiting on response persistence. |
| `resilient_background: bool = False` | Permit recovery of eligible background work without selecting background execution. |

Do not interpret a history limit of `None` as unlimited, map it to `-1`, or raise the dependency floor
to obtain a particular SDK default. History caps do not limit tokens, turns, retention, or checkpoints.
Heartbeats are not model or request timeouts.

Configure inference defaults on agents and clients, not through host `default_model`. Do not expose
host span callbacks, server-version stamping, or steering settings. Retain framework observability
and keep steering disabled. Removing host defaults does not redefine caller-supplied request models
or other request-option precedence.

### Approvals and consent

The native agent owns approval tracking, pending snapshots, policy decisions, binding, consumption,
and execution in its `AgentSession`. Hosting persists the complete session rather than implementing a
second approval store or a Foundry-specific approval dictionary in session state.
Native workflow pending authority remains checkpoint-owned.

AgentServer's wire IDs differ from native approval IDs. Retain only transport correlation in the
response item's internal metadata; it is not executable authority. The native session must still
contain the matching pending request. Save that session before publishing a resumable approval.
Remove the separate approval-store configuration and exports without silently migrating old pending work.

This migration preserves Core's existing session-level guarantees. Durable single-consumption across
workers and independently restored old snapshots requires separate native session-store coordination.
Do not implement that guarantee in a hosting-specific approval manager.

The intended HTTP contract rejects incomplete hosted MCP approval sets before streaming, response headers,
`response.created`, or protected dispatch, without consuming pending authority. A complete batch may mix
approvals and rejections. Exact pre-header HTTP 400 behavior remains blocked on a suitable public SDK
validation hook under #9537; the native approval migration does not claim to implement that requirement.

Represent invocation-time OAuth consent as structured consent with incomplete response status.
Pair each emitted function call with one terminal result, preserve completed sibling results, and stop
later protected calls. Require `store=true` so continuation can retain the required state;
do not support ephemeral consent under `store=false`.

### Unresolved boundaries

Do not infer a single-target restriction or a multi-target router without a documented Foundry platform
contract. Request `model` is not implicitly an agent selector.

Broader option precedence and validation details require separate design. The host split does not
authorize removing existing hooks or applying workflow-only assumptions to regular agents.

Keep current dependency requirements and the steering guard until published-wheel compatibility and
concurrent queue-overflow behavior are verified. An upstream merge alone is not release evidence.
These decisions do not redesign Core, concurrency, checkpoints, retries, or external exactly-once execution.

## Consequences

- Public signatures identify execution models and their state owners.
- Shared internals avoid duplicate engines without obscuring public contracts.
- Request-aware factories support identity-dependent resources but require deliberate isolation and cleanup.
- The API migration breaks combined-host construction, wrapper hosting, unnamed or zero-argument agent factories, old parser/request names, source literals, and the storage-backend alias.
- SDK constructor arguments move from arbitrary top-level keywords to the explicit, unvalidated `agent_server_kwargs` mapping. The public SDK options bag is replaced by supported first-class settings.
- Settings, authority, and consent changes require their own implementation and correctness validation; recording a decision does not establish that it has shipped.

## Validation

Cover public imports and signatures, invalid construction before SDK side effects, sync/async factory
invocation, failure/cancellation cleanup, and rejection of shared workflow resources.
Exercise streaming and non-streaming execution, session/checkpoint continuation, pending replies,
and model-free process crash/recovery. Validate maintained samples against public exports.
Offline checks do not establish live Foundry deployment compatibility.
