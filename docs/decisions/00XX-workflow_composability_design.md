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

## Current State
- High-level builders (ConcurrentBuilder, SequentialBuilder, group chat variants) emit a finished Workflow; the graph is immutable and cannot be extended directly.
- WorkflowExecutor already wraps a Workflow as an Executor; composition is possible but requires manual wrapping and does not provide fluent sugar on builders.
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
- Keep fragment inlining but make connection verbs explicit and fluent via `.connect(...)`.
- `WorkflowConnection`:
  - `builder`: WorkflowBuilder holding the fragment wiring.
  - `entry`: canonical entry executor id.
  - `exits`: executor ids that are safe to target (default terminal outputs or last adapters).
  - `contract`: input/output type sets plus semantics tags for validation (reuses Option 3 contracts if available).
- Production:
  - High-level builders expose `.as_connection()` returning connection metadata without building a Workflow.
  - Built workflows expose `.as_connection()` by cloning topology into a new builder (immutable source).
- Composition API (renamed for clarity):
  - Single verb: `connect(...)` handles both merge and wiring. No `add_fragment`.
  - Accepted inputs:
    - `connect(fragment_or_workflow, *, prefix=None, source=None, target=None, adapter=None)`
    - `connect(source_executor_id_or_port, target_executor_id_or_port, *, adapter=None)`
  - If `fragment_or_workflow` is provided:
    - Merge its builder into the caller with optional `prefix` to avoid ID collisions.
    - Return a handle with `.start` and `.outputs` to allow chaining.
    - If `source` is provided, wire `source -> fragment.start`.
    - If `target` is provided, wire `fragment.outputs[0] -> target` (or all outputs if specified).
  - `FragmentHandle.start` alias for entry; `FragmentHandle.outputs` alias for exits to keep names concise in chaining.
  - Optional chaining: `builder.connect(orchestrator, analysis.start).connect(analysis.outputs[0], aggregator)`.
- Naming shift: prefer `connect` over `add_edge` for user-facing fluent APIs; keep `add_edge` under the hood for compatibility.
- Type safety:
  - `connect` enforces compatibility between source output types and target input types (or fragment contract).
  - Allow optional `adapter` param to inject a converter executor inline if strict types differ (compatible with Option 3 registry).
- Example:

```python
analysis = (
    ConcurrentBuilder()
    .participants([operation, compliance])
    .as_connection()
)

builder = WorkflowBuilder()
analysis_handle = builder.connect(analysis, prefix="analysis")  # merge + handle
builder.connect(orchestrator, analysis_handle.start)
builder.connect(analysis_handle.outputs[0], aggregator_executor)
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
normalize_handle = builder.add_connection(normalize_connection, prefix="prep")
summarize_handle = builder.add_connection(summarize_connection, prefix="summary")
builder.connect(normalize_handle.output_points[0], summarize_handle.start_id)
builder.set_start_executor(normalize_handle.start_id)

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
- Option 2: Code included for connect-first Option 2 with `.as_connection()` and typed `ConnectionHandle`/`ConnectionPoint`, plus samples and tests.

### Optional Add-ons
- Stage 2: Harden type contracts and adapters (Option 3) on top of connections: registry for converters, explicit adapter insertion toggles, richer diagnostics.
- Stage 3: Add port semantics (Option 4) to label connection points and reduce ambiguities for multi-exit/multi-input executors.
- Stage 4: Revisit WorkflowExecutor sugar (Option 1) for cases where isolation boundaries are preferred over inlining; keep the API minimal and adapter-aware.

## Compatibility and Behavior Notes
- Checkpointing: WorkflowExecutor already supports checkpoints via wrapped workflow. Connection merge must carry over checkpoint storage configuration when cloning, but runtime checkpoint overrides should still flow through parent run() parameters.
- RequestInfo propagation: WorkflowExecutor currently surfaces SubWorkflowRequestMessage; connection merge must ensure request edges remain intact and reachable after ID renaming.
- Observability: retain executor IDs that describe provenance; id_prefix in connection merge prevents collisions while keeping names interpretable in traces.
- Streaming semantics: nested workflows already stream through WorkflowExecutor; merged fragments rely on existing superstep scheduling so no change is needed.
- Backward compatibility: existing builder APIs remain valid; new helpers are additive.
