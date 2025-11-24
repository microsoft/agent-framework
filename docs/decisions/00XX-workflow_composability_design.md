---
# These are optional elements. Feel free to remove any of them.
status: in-progress
contact: moonbox3
date: 2025-11-21 {YYYY-MM-DD when the decision was last updated}
deciders: bentho, taochen, jacob, victor, peter
consulted: eduard, dmytro, gil, mark
informed: team
---

# Workflow Composability Design

## Objective
- Enable fluent composition of workflow builders so downstream edges can be attached without rewriting high-level patterns.
- Preserve strict type compatibility between node outputs and downstream inputs (ChatMessage chains today, other payloads later).
- Reuse existing primitives (WorkflowBuilder, WorkflowExecutor, Workflow.as_agent) rather than inventing new one-off constructs.
- Keep checkpointing, request/response handling, and observability semantics intact across composed graphs.

## Terminology
- Workflow: an immutable, built artifact that can be executed or wrapped (e.g., by WorkflowExecutor). Composition should not mutate an existing Workflow.
- WorkflowBuilder: the mutable authoring surface for wiring executors, merging graphs, and validating types. All composition logic lives here.
- High-level builders: convenience builders (ConcurrentBuilder, SequentialBuilder, group chat variants) that internally use WorkflowBuilder; they will share a base mixin that provides `.as_connection()` so the composition API is consistent.

## Current State
- High-level builders (ConcurrentBuilder, SequentialBuilder, group chat variants) emit a finished Workflow; the graph is immutable and cannot be extended directly.
- WorkflowExecutor already wraps a Workflow as an Executor; composition is possible but requires manual wrapping and does not provide fluent sugar on builders.
- Sub-workflows today are therefore possible via WorkflowExecutor, but the nested boundary brings double superstep scheduling, separate checkpoints, and manual edge wiring; there is no inline-merge path that keeps a single workflow boundary.
- Workflow.as_agent is convenient for agent-based chaining but forces list[ChatMessage] inputs and loses internal workflow outputs unless they are ChatMessages.
- Type compatibility is enforced by WorkflowBuilder during validation, but only within a single builder instance; cross-workflow composition relies on developers hand-wiring compatible adapters.

## Requirements
- Compose multiple workflows (built from any builder) as first-class nodes inside a parent graph.
- Allow attaching extra edges before or after high-level builder wiring (e.g., add a post-aggregator executor to ConcurrentBuilder).
- Maintain type safety: downstream inputs must match upstream outputs; provide adapters for deliberate type reshaping.
- Namespacing and ID hygiene to avoid collisions when merging graphs.
- Preserve existing behaviors: checkpoint support, request_info propagation, and event traces must survive composition.

## Option 1: WorkflowExecutor-Centric Composition Helpers
- Add a fluent creation path for WorkflowExecutor to remove manual boilerplate:
  - `Workflow.as_executor(id: str | None = None, *, allow_direct_output: bool = False, adapter: Callable[[Any], Any] | None = None) -> WorkflowExecutor`
  - `WorkflowBuilder.add_workflow(source_workflow: Workflow, *, id: str | None = None, allow_direct_output: bool = False, adapter: Callable[[Any], Any] | None = None) -> Self`
- Behavior:
  - `allow_direct_output=False` keeps current semantics (sub-workflow outputs become messages to downstream nodes). `True` forwards sub-workflow outputs as workflow outputs; parent edges receive nothing.
  - Optional `adapter` transforms sub-workflow outputs before routing (e.g., list[ChatMessage] -> MyAnalysisSummary). Adapter runs inside the WorkflowExecutor to preserve type validation.
  - Input type compatibility is checked using existing is_type_compatible between parent edge source and sub-workflow start executor types; adapter output types are validated before send_message.
- Intent: this is strictly sugar over the existing `WorkflowExecutor(workflow, id=..., ...)` pattern; edges are still attached with `add_edge(...)` and no new lifecycle semantics are introduced.
- Example:

```python
analysis = (
    ConcurrentBuilder()
    .participants([operation, compliance])
    .build()
    .as_executor(id="analysis", adapter=pick_latest_assistant)
)

workflow = (
    WorkflowBuilder()
    .add_edge(orchestrator, analysis)
    .add_edge(analysis, aggregator_executor)
    .set_start_executor(orchestrator)
    .build()
)
```
- Pros: minimal code surface; reuses WorkflowExecutor and existing validation. Cons: maintains nested execution boundary (double superstep scheduling, separate checkpoint lineage), and post-build graph edits are still indirect.

## Option 2: Inline Fragments With Builder Merge (connect-first API)
- Keep fragment inlining but make connection verbs explicit and fluent via `.add_workflow(...)` for fragments and `.connect(...)` for edges.
- `WorkflowConnection` (thin wrapper, mainly for cases where the source builder is not directly available):
  - `builder`: WorkflowBuilder holding the fragment wiring.
  - `entry`: canonical entry executor id.
  - `exits`: executor ids that are safe to target (default terminal outputs or last adapters).
  - `contract`: input/output type sets plus semantics tags for validation (reuses Option 3 contracts if available).
- Production:
  - High-level builders expose `.as_connection(prefix: str | None = None)` returning connection metadata without building a Workflow. Prefix defaults to the builder's `name` if set.
  - Built workflows expose `.as_connection(prefix: str | None = None)` by cloning topology into a new builder (immutable source); prefix defaults to the workflow `name`.
  - All high-level builders share the same mixin so `.as_connection()` exists regardless of the concrete builder type.
- Composition API (renamed for clarity):
  - `handle = builder.add_workflow(fragment: WorkflowBuilder | Workflow | WorkflowConnection, *, prefix=None)` merges the fragment into the caller and returns a handle with `.start`/`.outputs`. If `prefix` is omitted, the fragment's `name` (or class name) is used to avoid collisions. `add_workflow` calls `.as_connection(prefix)` internally so callers rarely invoke `.as_connection()` themselves.
  - `builder.connect(source_executor_id_or_port, target_executor_id_or_port, *, adapter=None)` wires two existing nodes/ports together; use the handle returned from `add_workflow` to address fragment entry/exit points.
  - Internally this is still the existing `add_edge` machinery plus a builder merge; there are no new edge types or runner semantics.
- Defaults and safety:
  - Reusing the same fragment multiple times yields independent cloned builders so immutability is preserved.
  - Multi-exit fragments require explicit `handle.outputs[...]` selection; no implicit first-exit wiring.
  - Collision avoidance uses `prefix or fragment.name` with a deterministic fallback (`fragment-{n}`) when no name is present.
  - Connection handles freeze only entry/exit metadata; the graph remains a WorkflowBuilder to avoid duplicating builder APIs.
- Caller knowledge:
  - When you control both builders, you can rely only on the surfaced `start`/`outputs` handle and continue to use `add_edge`/`connect`; internal executor IDs remain encapsulated.
  - For hosted/pre-built workflows where the builder is hidden, the connection exposes the public entry/exit surface and can later map to different endpoints when hosted.
- Example:

```python
analysis_builder = ConcurrentBuilder().participants([operation, compliance])
builder = WorkflowBuilder()
analysis = builder.add_workflow(analysis_builder)  # prefix defaults to analysis_builder.name/class
builder.connect(orchestrator, analysis.start)
builder.connect(analysis.outputs[0], aggregator_executor)
workflow = builder.set_start_executor(orchestrator).build()
```
- Pros: single workflow boundary, explicit connect vocabulary, compatibility with port semantics later. Cons: still needs ID renaming during merge and clear immutability rules for fragments.

### Fluent pattern illustration with connect-only (option 2)

```python
normalize_connection = (
    WorkflowBuilder()
    .add_edge(Normalize(id="normalize"), Enrich(id="enrich"))
    .set_start_executor("normalize")
    .as_connection()
)

summarize_connection = (
    WorkflowBuilder()
    .add_edge(Summarize(id="summarize"), Publish(id="publish"))
    .set_start_executor("summarize")
    .as_connection()
)

builder = WorkflowBuilder()
normalize_handle = builder.add_workflow(normalize_connection, prefix="prep")
summarize_handle = builder.add_workflow(summarize_connection, prefix="summary")
builder.connect(normalize_handle.outputs[0], summarize_handle.start)
builder.set_start_executor(normalize_handle.start)

workflow = builder.build()
print("Outputs:")
async for event in workflow.run_stream("  Hello Composition  "):
    if isinstance(event, WorkflowOutputEvent):
        print(event.data)
```

## Option 3: Typed Adapters and Contracts
- Provide first-class adapter executors to bridge mismatched but intentionally compatible types instead of ad-hoc callbacks:
  - `builder.add_adapter(source, target, adapter_fn)` sugar that injects a small Executor running adapter_fn; validated via is_type_compatible on adapter outputs.
  - Offer canned adapters for common shapes: `ConversationToText`, `TextToConversation`, `MessagesToStructured[T]`, mirroring existing _InputToConversation/_ResponseToConversation patterns.
- Expose explicit type contracts on fragments/workflows:
  - `WorkflowContract` capturing `input_types`, `output_types`, and optional `output_semantics` (e.g., “conversation”, “agent_response”, “request_message”).
  - Composition helpers use contracts to fail fast or select the right canned adapter.
- Note: this remains sugar for “add a new executor that transforms the data”; the value is deterministic naming, validation, and observability of these adapters instead of one-off inline callables.
- Pros: predictable type-safe bridges and better error messages. Cons: adds small surface area but aligns with existing adapter executors already used inside SequentialBuilder.

## Option 4: Port-Based Interfaces and Extension Points
- Elevate executor I/O to named ports with declared types, making composition addressable:
  - Executors expose `ports: dict[str, PortSpec]` where PortSpec includes direction (in/out), type set, and optional semantics tag (`conversation`, `aggregate`, `request`, `control`).
  - Builders produce a `WorkflowPorts` manifest identifying exposed ports (entry, exit, extension points) instead of only start/terminal nodes.
  - New APIs: `builder.connect(source=(node_id, "out:conversation"), target=(node_id, "in:conversation"))` with validation on port types/semantics.
- High-level builders declare explicit extension points:
  - ConcurrentBuilder exposes `dispatch_out`, `fan_in_in`, `aggregator_out`.
  - SequentialBuilder exposes `input_normalizer_out`, `final_conversation_out`.
  - Group chat exposes manager in/out, participant in/out.
- Composition uses ports rather than raw executor IDs, enabling fluent “attach after aggregator” semantics without cloning graphs or nesting:
  - Hosted/remote workflows could expose their ports to let callers bind different endpoints per input/output when instantiating a hosted instance.
  - Scope control: port specs are metadata carried by builders/manifest; low-level executors stay unchanged unless explicitly annotated, keeping the API surface small for non-port users.
  - Port metadata is derived from builder-declared wiring (or optional static executor annotations) rather than a new runtime interface on Executor implementations.

```python
concurrent = ConcurrentBuilder().participants([...]).build_ports()
builder = WorkflowBuilder()
analysis = builder.inline(concurrent, prefix="analysis")
builder.connect(analysis.port("aggregator_out"), summarizer.port("in"))
builder.connect(orchestrator.port("out"), analysis.port("entry"))
```
- Pros: explicit extension surface, strong type+semantics validation, avoids nested runner overhead. Cons: requires port metadata on executors and new connect API; existing builder wiring must annotate ports without breaking current ID behavior.

## Option 5: Automatic Converter Insertion via Registry
- Introduce a registry of safe converters between message shapes (e.g., `list[ChatMessage] -> str`, `AgentExecutorResponse -> list[ChatMessage]`, `Any -> ChatMessage` with Role defaults).
- WorkflowBuilder gains optional auto-convert mode:
  - On edge validation failure, consult registry for a single-step converter; if found, auto-insert a lightweight adapter executor (generated with stable ID naming).
  - Developers can opt into explicit converter selection: `builder.add_edge(a, b, allow_auto_adapter=True)` or `with_auto_adapters(converter_registry=...)`.
- Registry seeded with built-in converters mirroring current adapters; users can register domain-specific converters with precedence and safety labels (lossless vs lossy).
- Pros: reduces composition friction when combining workflows with slightly different output shapes; preserves validation rigor with explicit control. Cons: auto-insertion can obscure graph shape unless surfaced in observability; must keep deterministic ordering to avoid non-reproducible builds.

## Option 6: Graph Rewrite Pipeline (Plan-Time Rewriters)
- Treat built graphs as IR and apply rewriting passes before final Workflow creation:
  - Passes can inline sub-workflows, insert adapters, rename IDs for collision avoidance, or hoist extension points.
  - Rewriters operate on an intermediate `WorkflowPlan` (edge groups + metadata + port semantics) produced by all builders.
  - Users can register rewrites or select presets: `WorkflowBuilder().with_rewriters([InlineSingleUseWorkflows, InsertCheckpointHooks])`.
- Composition story:
  - Build parent plan with placeholder nodes referencing child plans (from any builder).
  - Run rewrite pipeline to inline or wrap depending on policy (performance vs isolation).
  - Final validation executes on rewritten plan only.
- Pros: maximizes flexibility; enables policy-driven composition (e.g., inline small subgraphs, nest large ones); keeps public API compact by centralizing transformation. Cons: higher conceptual load; needs deterministic, debuggable rewrite tracing to avoid “hidden magic.”

## Option 7: Declarative Contracts and Compilation Targets
- Define a declarative DSL (JSON/YAML/Python builders) for workflow composition with explicit schema contracts:
  - Contracts specify allowed input/output schemas (Pydantic-like), conversion policies, checkpoint scopes, and observability hints.
  - Compilation targets:
    - `inline` target produces a single Workflow (like Option 2 but driven by declarative spec).
    - `nested` target produces WorkflowExecutor-wrapped subgraphs (Option 1) when isolation or fault domains require boundaries.
  - Builders emit contract metadata during `build_contract()`; composition compiles contracts into a concrete topology via selected target.
- Pros: clear separation between design-time contract authoring and runtime topology; can later feed into codegen or docs. Cons: adds a contract layer and a compiler; risk of over-abstraction if not scoped tightly.

### Feasibility, gotchas, trade-offs for Option 1
- Isolation vs overhead: nested WorkflowExecutor keeps boundaries but adds superstep indirection and separate checkpoint lineage; may complicate observability and latency.
- Type visibility: adapters help but nested workflows obscure internal types; without contract export, parent validation sees only outer signatures.
- Request propagation: SubWorkflowRequestMessage semantics differ from inlining; callers must choose boundaries carefully.
- Adapter risks: inline callbacks can hide lossy conversions; add explicit adapter typing and trace visibility.

### Feasibility, gotchas, trade-offs for Option 2
- ID hygiene: merging fragments demands deterministic prefixing and collision detection. Need stable rules (e.g., `prefix::original_id`) and clear errors when user-provided prefixes collide.
- Mutability: fragments must be immutable; reusing a fragment handle across builders should clone to avoid shared state mutation. Otherwise silent edge duplication risk.
- Exit disambiguation: multi-exit fragments require explicit target selection; defaulting to `outputs[0]` is dangerous if ordering changes. Enforce explicit output selection when len(outputs) > 1.
- Type contracts: connect must validate fragment contracts. If no compatible exit/input pairing exists, fail fast with actionable diagnostics listing expected vs provided types.
- Adapters: optional adapter insertion is helpful but must be observable. Emit trace breadcrumbs and deterministic IDs for auto-inserted adapters to keep debugging sane.
- Checkpointing: merged graphs must reconcile checkpoint storage precedence (parent vs fragment). Graph signature hashing must include prefixed IDs to keep validation aligned with saved checkpoints.
- RequestInfo behavior: inlined fragments drop the WorkflowExecutor boundary; if downstream relies on SubWorkflowRequestMessage semantics, behavior changes. Document when to inline vs wrap.
- Validation cost: large merges can inflate validation time; consider incremental validation caches keyed by fragment signature + prefix.
- Debuggability: connect sugar expands to multiple edges; provide graph inspection/dump after connect so users can audit the final topology.

### Feasibility, gotchas, trade-offs for Option 3
- Adapter sprawl: registry needs governance to avoid conflicting converters; precedence and safety (lossless vs lossy) must be enforced.
- Hidden rewrites: auto-inserted adapters change graph shape; must emit diagnostics and keep deterministic IDs.
- Schema drift: typed adapters rely on accurate annotations; missing or broad types (Any) reduce safety.

### Feasibility, gotchas, trade-offs for Option 4
- Port taxonomy: requires consistent semantics tagging across executors; retrofitting existing nodes needs care.
- Ergonomics: port-qualified connect can be verbose; needs sensible defaults for single-port executors.
- Validation: port type sets vs executor type sets must stay in sync; risk of divergence if one side changes without the other.

### Feasibility, gotchas, trade-offs for Option 5
- Auto-conversion noise: over-eager adapters could mask type mismatches; require opt-in or warnings on insertion.
- Order/determinism: converter selection must be deterministic; ambiguity between multiple valid converters needs resolution strategy.
- Observability: injected adapters must appear in traces/visualizations to avoid debugging blind spots.

### Feasibility, gotchas, trade-offs for Option 6
- Rewrite complexity: transformation pipeline can become opaque; needs tracing of applied passes and resulting graphs.
- Determinism: rewrites must be stable across runs; otherwise checkpoint signatures and tests break.
- Debug/authoring: users need tooling to inspect IR before/after rewrites; without it, “magic” feels brittle.

### Feasibility, gotchas, trade-offs for Option 7
- DSL scope: risk of over-abstraction; contracts must stay aligned with runtime capabilities to avoid split-brain specs.
- Compilation targets: inline vs nested strategies need clear selection rules; inconsistent outcomes hurt predictability.
- Tooling cost: contract authoring, validation, and codegen add maintenance overhead; ensure payoff justifies complexity.

## Recommendation
- Option 2: proceed with `add_workflow(...)` + `connect(...)`, default prefixing from workflow/builder name, shared `.as_connection()` mixin on all high-level builders, and typed `ConnectionHandle`/`ConnectionPoint` handles. Samples and tests cover both builder and workflow inputs.

### Optional Add-ons
- Stage 2: Harden type contracts and adapters (Option 3) on top of connections: registry for converters, explicit adapter insertion toggles, richer diagnostics.
- Stage 3: Add port semantics (Option 4) to label connection points and reduce ambiguities for multi-exit/multi-input executors.
- Stage 4: Revisit WorkflowExecutor sugar (Option 1) for cases where isolation boundaries are preferred over inlining; keep the API minimal and adapter-aware.

## Compatibility and Behavior Notes
- Checkpointing: WorkflowExecutor already supports checkpoints via wrapped workflow. Connection merge must carry over checkpoint storage configuration when cloning, but runtime checkpoint overrides should still flow through parent run() parameters.
- RequestInfo propagation: WorkflowExecutor currently surfaces SubWorkflowRequestMessage; connection merge must ensure request edges remain intact and reachable after ID renaming.
- Observability: retain executor IDs that describe provenance; prefixing via fragment `name` keeps traces readable while avoiding collisions.
- Streaming semantics: nested workflows already stream through WorkflowExecutor; merged fragments rely on existing superstep scheduling so no change is needed.
- Backward compatibility: existing builder APIs remain valid; `add_workflow`/`connect` are additive and degrade to explicit `add_edge` usage when desired.
