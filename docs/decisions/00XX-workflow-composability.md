---
status: in-progress
contact: moonbox3
date: 2026-01-20
deciders: bentho, taochen, jacob, victor, peter
consulted: eduard, dmytro, gil, mark
informed: team
---

# Workflow Composability Design

## Table of Contents

- [Problem Statement](#problem-statement)
- [Goals](#goals)
- [Current State](#current-state)
- [Proposed API](#proposed-api)
  - [OrchestrationBuilder Protocol](#orchestrationbuilder-protocol)
  - [Core Addition: `add_workflow()`](#core-addition-add_workflow)
  - [Usage](#usage)
- [Type Safety](#type-safety)
- [Implementation](#implementation)
  - [How `add_workflow()` Works Internally](#how-add_workflow-works-internally)
  - [How `add_edge()` Resolves Logical IDs](#how-add_edge-resolves-logical-ids)
  - [Extracting Builder from High-Level Builders](#extracting-builder-from-high-level-builders)
- [What We're NOT Doing](#what-were-not-doing)
- [Migration](#migration)
- [Open Questions](#open-questions)
- [Alternatives Considered](#alternatives-considered)
- [Design Decisions](#design-decisions)
  - [Type Validation with `yield_output` vs `send_message`](#type-validation-with-yield_output-vs-send_message)
- [Implementation Phases](#implementation-phases)

---

## Problem Statement

Users want to extend high-level builder patterns in two ways:

1. **Add pre/post-processing** - Insert custom executors before or after a high-level pattern (e.g., validate input before ConcurrentBuilder, format output after)

2. **Combine patterns** - Chain multiple high-level builders together (e.g., ConcurrentBuilder for analysis, then SequentialBuilder for summarization)

Today, both require writing custom orchestrator executors that manually dispatch messages and collect results.

**What users want to write:**

```python
# Use case 1: Add preprocessing to a high-level pattern
analysis = ConcurrentBuilder().participants([analyzer1, analyzer2])

workflow = (
    WorkflowBuilder()
    .register_executor(InputValidator, name="validator")
    .add_workflow(analysis, id="analysis")
    .register_executor(OutputFormatter, name="formatter")
    .add_edge("validator", "analysis")
    .add_edge("analysis", "formatter")
    .set_start_executor("validator")
    .build()
)

# Use case 2: Chain high-level patterns together
analysis = ConcurrentBuilder().participants([analyzer1, analyzer2])
summary = SequentialBuilder().participants([summarizer])

workflow = (
    WorkflowBuilder()
    .add_workflow(analysis, id="analysis")
    .add_workflow(summary, id="summary")
    .add_edge("analysis", "summary")
    .build()
)
```

**What's required today:**

Direct composition of high-level builders is not supported. The closest pattern requires a custom orchestrator executor that manually dispatches work and collects results:

```python
class PipelineOrchestrator(Executor):
    @handler
    async def start(self, input_data: str, ctx: WorkflowContext) -> None:
        await ctx.send_message(input_data, target_id="analysis")

    @handler
    async def handle_analysis_result(
        self, result: list[ChatMessage], ctx: WorkflowContext
    ) -> None:
        await ctx.send_message(result, target_id="summary")

    @handler
    async def handle_summary_result(
        self, result: list[ChatMessage], ctx: WorkflowContext
    ) -> None:
        await ctx.yield_output(result)

workflow = (
    WorkflowBuilder()
    .register_executor(PipelineOrchestrator, name="orchestrator")
    .register_executor(lambda: WorkflowExecutor(analysis.build(), id="analysis"), name="analysis")
    .register_executor(lambda: WorkflowExecutor(summary.build(), id="summary"), name="summary")
    .add_edge("orchestrator", "analysis")
    .add_edge("analysis", "orchestrator")
    .add_edge("orchestrator", "summary")
    .add_edge("summary", "orchestrator")
    .set_start_executor("orchestrator")
    .build()
)
```

## Goals

1. **Simple composition** - Combine workflows with minimal boilerplate
2. **Pythonic API** - Feels natural, no new concepts to learn
3. **Type safety** - Fail at build time with clear errors if types don't match
4. **Preserve semantics** - Checkpointing, request/response, observability work correctly
5. **Backward compatible** - Existing code continues to work

## Current State

| Component | Status | Notes |
|-----------|--------|-------|
| WorkflowBuilder | Complete | Full fluent API for graph construction |
| WorkflowExecutor | Complete | Wraps workflow as executor (nested composition) |
| High-level builders | Complete | ConcurrentBuilder, SequentialBuilder, GroupChatBuilder, etc. |
| `add_workflow()` | **Missing** | No convenience method for composition |
| Type validation across workflows | **Missing** | No validation that connected workflows have compatible types |

---

## Proposed API

### OrchestrationBuilder Protocol

High-level orchestration patterns share a common interface: they have a `build()` method that returns a `Workflow`. We define a protocol to capture this:

```python
class OrchestrationBuilder(Protocol):
    """Protocol for high-level orchestration pattern builders.

    Orchestration builders provide pre-wired multi-agent patterns:
    - ConcurrentBuilder  (fan-out/fan-in)
    - SequentialBuilder  (chain with shared context)
    - GroupChatBuilder   (orchestrator-directed conversation)
    - HandoffBuilder     (decentralized agent routing)
    - MagenticBuilder    (plan-based orchestration)

    Note: WorkflowBuilder is NOT an OrchestrationBuilder. It's the low-level
    primitive used to construct these patterns. add_workflow() accepts both
    OrchestrationBuilder and WorkflowBuilder, but they serve different purposes.
    """

    def build(self) -> Workflow: ...
```

This allows `add_workflow()` to accept any current or future orchestration pattern without explicitly listing them.

### Core Addition: `add_workflow()`

```python
class WorkflowBuilder:
    def add_workflow(
        self,
        source: OrchestrationBuilder | WorkflowBuilder,
        *,
        id: str,
    ) -> Self:
        """Merge an orchestration pattern or workflow builder into this builder.

        Args:
            source: An OrchestrationBuilder (ConcurrentBuilder, etc.) or WorkflowBuilder
            id: Logical identifier for the merged workflow.
                Used with add_edge() and set_start_executor().
                Internal executor IDs are prefixed with this id.

        Returns:
            Self for method chaining.

        The `id` becomes a logical identifier that add_edge() and set_start_executor()
        can resolve automatically:
        - add_edge("analysis", "summary") wires analysis's exit to summary's entry
        - set_start_executor("analysis") sets analysis's entry as the start
        """
        ...
```

### Usage

```python
# Simple linear composition
analysis = ConcurrentBuilder().participants([agent1, agent2])
summary = SequentialBuilder().participants([summarizer])

workflow = (
    WorkflowBuilder()
    .add_workflow(analysis, id="analysis")
    .add_workflow(summary, id="summary")
    .add_edge("analysis", "summary")  # Framework resolves entry/exit points
    .set_start_executor("analysis")   # Framework knows this means analysis's entry
    .build()
)
```

```python
# Composition with custom executors
workflow = (
    WorkflowBuilder()
    .register_executor(Preprocessor, name="preprocess")
    .add_workflow(analysis_builder, id="analysis")
    .register_executor(Postprocessor, name="postprocess")
    .add_edge("preprocess", "analysis")
    .add_edge("analysis", "postprocess")
    .set_start_executor("preprocess")
    .build()
)
```

```python
# Branching based on classifier output
workflow = (
    WorkflowBuilder()
    .register_executor(Classifier, name="classifier")
    .add_workflow(fast_path, id="fast")
    .add_workflow(slow_path, id="slow")
    .add_switch_case_edge_group(
        "classifier",
        [
            Case(condition=lambda r: r.confidence > 0.9, target="fast"),
            Default(target="slow"),
        ]
    )
    .set_start_executor("classifier")
    .build()
)
```

---

## Type Safety

### The Problem

Each high-level builder has implicit input/output types:

| Builder | Input Types | Output Types |
|---------|-------------|--------------|
| ConcurrentBuilder | `str`, `ChatMessage`, `list[ChatMessage]` | `list[ChatMessage]` |
| SequentialBuilder | `str`, `ChatMessage`, `list[ChatMessage]` | `list[ChatMessage]` |
| GroupChatBuilder | `str`, `ChatMessage`, `list[ChatMessage]` | `list[ChatMessage]` |
| Custom Executor | Whatever handlers accept | Whatever handlers send |

If you connect workflows with incompatible types, messages silently won't be delivered (no handler matches).

### Proposed Solution

Add type metadata to builders and validate at `build()` time:

```python
# Internal: each builder knows its contract
class ConcurrentBuilder:
    @property
    def _input_types(self) -> set[type]:
        return {str, ChatMessage, list[ChatMessage]}

    @property
    def _output_types(self) -> set[type]:
        return {list[ChatMessage]}
```

When `WorkflowBuilder.build()` validates edges, check type compatibility:

```python
# At build() time, for each edge crossing workflow boundaries:
if not _types_compatible(source_output_types, target_input_types):
    raise TypeError(
        f"Type mismatch: '{source_id}' outputs {source_output_types} "
        f"but '{target_id}' expects {target_input_types}"
    )
```

### Error Messages

Good error messages are critical:

```
TypeError: Cannot connect 'analysis/aggregator' to 'custom_processor':
  - 'analysis/aggregator' outputs: list[ChatMessage]
  - 'custom_processor' accepts: AnalysisResult, dict

To fix this, either:
  1. Change 'custom_processor' to accept list[ChatMessage]
  2. Add an adapter executor between them that converts the types
```

---

## Implementation

### How `add_workflow()` Works Internally

1. **Extract graph info** from the source builder (executors, edges, start/end points)
2. **Prefix all executor IDs** with the provided `id` parameter
3. **Register executors** into the parent builder with prefixed IDs
4. **Copy edge groups** with prefixed IDs
5. **Track logical ID mapping** for entry/exit point resolution

```python
def add_workflow(
    self,
    source: OrchestrationBuilder | WorkflowBuilder,
    *,
    id: str,
) -> Self:
    # Extract WorkflowBuilder from source (or use directly if already WorkflowBuilder)
    inner_builder = self._extract_builder(source)

    # Prefix all IDs
    prefix = id

    # Copy executors with prefixed IDs
    for exec_id, executor in inner_builder._executors.items():
        prefixed_id = f"{prefix}/{exec_id}"
        # Clone executor with new ID
        cloned = executor._clone_with_id(prefixed_id)
        self._executors[prefixed_id] = cloned

    # Copy edge groups with prefixed IDs
    for edge_group in inner_builder._edge_groups:
        prefixed_group = edge_group._with_prefix(prefix)
        self._edge_groups.append(prefixed_group)

    # Track logical ID -> entry/exit point mapping
    entry_id = f"{prefix}/{inner_builder._start_executor_id}"
    exit_ids = [f"{prefix}/{eid}" for eid in inner_builder._terminal_executor_ids]
    self._workflow_mappings[id] = WorkflowMapping(entry=entry_id, exits=exit_ids)

    return self
```

### How `add_edge()` Resolves Logical IDs

When `add_edge()` receives an ID, it checks if it's a logical workflow ID:

```python
def add_edge(self, source: str, target: str) -> Self:
    # Resolve logical IDs to actual executor IDs
    resolved_source = self._resolve_exit(source)   # Use exit point if workflow ID
    resolved_target = self._resolve_entry(target)  # Use entry point if workflow ID

    # ... existing edge creation logic with resolved IDs ...

def _resolve_exit(self, id: str) -> str:
    """Resolve ID to exit point if it's a workflow ID, otherwise return as-is."""
    if id in self._workflow_mappings:
        mapping = self._workflow_mappings[id]
        if len(mapping.exits) != 1:
            raise ValueError(
                f"Workflow '{id}' has {len(mapping.exits)} exit points. "
                f"Use explicit IDs: {mapping.exits}"
            )
        return mapping.exits[0]
    return id

def _resolve_entry(self, id: str) -> str:
    """Resolve ID to entry point if it's a workflow ID, otherwise return as-is."""
    if id in self._workflow_mappings:
        return self._workflow_mappings[id].entry
    return id
```

This approach:
- **Keeps the simple case simple**: `add_edge("analysis", "summary")` just works
- **Handles ambiguity explicitly**: If a workflow has multiple exits, user must specify which one
- **Preserves escape hatch**: Users can still use full IDs like `"analysis/aggregator"` when needed

### Extracting Builder from High-Level Builders

High-level builders don't currently expose their internal structure. Options:

**Option A: Add internal method to each builder**
```python
class ConcurrentBuilder:
    def _to_builder(self) -> WorkflowBuilder:
        """Build internal WorkflowBuilder without calling build()."""
        # Similar to build() but returns the builder, not the workflow
        ...
```

**Option B: Build and extract from Workflow**
```python
def _extract_builder(self, source) -> WorkflowBuilder:
    if isinstance(source, WorkflowBuilder):
        return source
    # For high-level builders, build then extract
    workflow = source.build()
    return workflow._to_builder()  # Reconstruct builder from workflow
```

**Recommendation: Option A** - cleaner, no round-trip through Workflow.

---

## What We're NOT Doing

To keep the design simple:

- **No new `connect()` method** - Use existing `add_edge()` with logical ID resolution
- **No public handle types** - Logical IDs and internal mappings are implementation details
- **No type adapter registry** - Users write adapter executors if needed
- **No auto-adapter insertion** - Explicit is better than implicit
- **No port semantics** - Over-engineering for current needs
- **No requirement to know internal executor names** - Logical IDs abstract this away

---

## Migration

### Before

```python
# Custom orchestrator required to chain two workflows
class PipelineOrchestrator(Executor):
    @handler
    async def start(self, data: str, ctx: WorkflowContext) -> None:
        await ctx.send_message(data, target_id="analysis")

    @handler
    async def handle_analysis_result(
        self, result: list[ChatMessage], ctx: WorkflowContext
    ) -> None:
        await ctx.send_message(result, target_id="summary")

    @handler
    async def handle_summary_result(
        self, result: list[ChatMessage], ctx: WorkflowContext
    ) -> None:
        await ctx.yield_output(result)

workflow = (
    WorkflowBuilder()
    .register_executor(PipelineOrchestrator, name="orchestrator")
    .register_executor(lambda: WorkflowExecutor(analysis.build(), id="analysis"), name="analysis")
    .register_executor(lambda: WorkflowExecutor(summary.build(), id="summary"), name="summary")
    .add_edge("orchestrator", "analysis")
    .add_edge("analysis", "orchestrator")
    .add_edge("orchestrator", "summary")
    .add_edge("summary", "orchestrator")
    .set_start_executor("orchestrator")
    .build()
)
```

### After

```python
# Direct composition - no custom orchestrator needed
workflow = (
    WorkflowBuilder()
    .add_workflow(analysis, id="analysis")
    .add_workflow(summary, id="summary")
    .add_edge("analysis", "summary")
    .set_start_executor("analysis")
    .build()
)
```

---

## Open Questions

1. **ID prefix separator**: `analysis/dispatcher` vs `analysis::dispatcher` vs `analysis.dispatcher`?
   - Proposal: `/` (familiar from paths, clear visual separator)

2. **What if source builder is used multiple times?**
   - Each `add_workflow()` call should clone the source to avoid shared state
   - Different `id` prefixes ensure no collisions

3. **Should `add_workflow()` accept a built `Workflow`?**
   - Useful for reusing a pre-built workflow
   - Requires extracting topology back into a builder (cloning executors)
   - Recommendation: Support it for flexibility

4. **How to handle checkpoint storage from merged builders?**
   - Proposal: Parent's checkpoint config takes precedence
   - Merged builders' checkpoint configs are ignored

---

## Alternatives Considered

### Alternative A: WorkflowExecutor Sugar Only

Add convenience methods to wrap workflows in `WorkflowExecutor` without changing execution semantics.

```python
class Workflow:
    def as_executor(self, id: str) -> WorkflowExecutor:
        return WorkflowExecutor(self, id=id)

# Usage
workflow = (
    WorkflowBuilder()
    .register_executor(lambda: analysis.build().as_executor("analysis"), name="analysis")
    .register_executor(lambda: summary.build().as_executor("summary"), name="summary")
    .add_edge("analysis", "summary")
    .build()
)
```

**Why not chosen:**
- Still requires `.build()` before composing
- Maintains nested execution boundary (double superstep scheduling, separate checkpoint lineage)
- Doesn't solve the core problem of needing a custom orchestrator for message routing
- Just syntactic sugar over existing `WorkflowExecutor(workflow, id=...)` pattern

### Alternative B: Connection Protocol with Explicit Metadata

Expose a `WorkflowConnection` wrapper and `as_connection()` method on all builders.

```python
class WorkflowConnection:
    builder: WorkflowBuilder
    entry: str
    exits: list[str]
    input_types: set[type]
    output_types: set[type]

class ConcurrentBuilder:
    def as_connection(self, prefix: str | None = None) -> WorkflowConnection:
        ...

# Usage
connection = analysis_builder.as_connection(prefix="analysis")
builder.add_workflow(connection)
builder.connect(connection.exits[0], other.entry)
```

**Why not chosen:**
- Exposes unnecessary abstraction to users (`WorkflowConnection`)
- Users must understand and call `as_connection()` explicitly
- Adds cognitive overhead without clear benefit
- `add_workflow()` can handle this internally

### Alternative C: Handle-Based API

Return a handle from `add_workflow()` with `.start` and `.end` properties for explicit wiring.

```python
h1 = builder.add_workflow(analysis, id="analysis")
h2 = builder.add_workflow(summary, id="summary")
builder.add_edge(h1.end[0], h2.start)  # Explicit entry/exit wiring
```

**Why not chosen:**
- Requires users to understand internal structure (`.start`, `.end[0]`)
- `.end[0]` is awkward - users shouldn't need to know about exit point lists
- Exposes implementation details that should be hidden
- Logical ID resolution provides the same functionality with simpler syntax

### Alternative D: New `connect()` Method

Add a `connect()` method alongside `add_edge()` specifically for workflow composition.

```python
builder.connect("analysis", "summary")  # Separate method for workflow connections
```

**Why not chosen:**
- Duplicates `add_edge()` functionality
- Adds API surface without clear benefit
- Users already know `add_edge()`
- Creates confusion about when to use `connect()` vs `add_edge()`
- Better to enhance `add_edge()` with logical ID resolution

### Alternative E: Port-Based Interfaces

Elevate executor I/O to named ports with declared types and semantics.

```python
class Executor:
    ports: dict[str, PortSpec]  # in/out, types, semantics

builder.connect(
    source=(analysis, "out:conversation"),
    target=(summary, "in:conversation")
)
```

**Why not chosen:**
- Significant complexity added to executor interface
- Requires retrofitting all existing executors
- Over-engineering for current needs
- Port semantics can be added later if needed

### Alternative F: Auto-Adapter Insertion

Automatically insert type adapters when connecting incompatible workflows.

```python
# Framework auto-inserts adapter if types don't match
builder.add_edge(text_output, chat_input)  # Auto-inserts TextToMessages adapter
```

**Why not chosen:**
- "Magic" behavior obscures graph structure
- Makes debugging harder (hidden executors)
- Users may not realize types are being converted
- Explicit adapters are clearer and more predictable

### Alternative G: Declarative Composition DSL

Define composition via YAML/JSON schema with explicit type contracts.

```yaml
workflows:
  analysis:
    builder: ConcurrentBuilder
    participants: [agent1, agent2]
  summary:
    builder: SequentialBuilder
    participants: [summarizer]

pipeline:
  - analysis -> summary
```

**Why not chosen:**
- Adds a new language/format to learn
- Requires tooling for validation and code generation
- Python code is already declarative enough
- Solve the simple problem first

---

## Design Decisions

### Type Validation with `yield_output` vs `send_message`

**Problem:** High-level builders like `ConcurrentBuilder` use `yield_output()` in their terminal executors (e.g., aggregator) to produce workflow output. However, when composing workflows via `add_workflow()`, edges connect the terminal executor to downstream executors. The type validation originally only checked `output_types` (types from `send_message()`), not `workflow_output_types` (types from `yield_output()`), resulting in spurious warnings.

**Options Considered:**

1. **Automatically swap aggregators when composing** - When `add_workflow()` is called, detect if the source has a terminal executor using `yield_output()` and swap it for one using `send_message()`.
   - **Rejected:** Too implicit. The same builder would behave differently standalone vs composed, making debugging difficult.

2. **Modify `_to_builder()` to use a forwarding aggregator** - Similar to option 1 but at the `_to_builder()` level.
   - **Rejected:** Same issues - hidden behavior change violates principle of least surprise.

3. **Enhance type validation to check `workflow_output_types`** - When validating edge type compatibility, if `output_types` is empty, fall back to `workflow_output_types`.
   - **Chosen:** Simple, explicit, no runtime behavior change. The validation becomes smarter without changing how executors work.

4. **Have runtime automatically forward `yield_output` data through edges** - Detect when an executor yields output but has outgoing edges, and forward that output as a message.
   - **Rejected:** Changes runtime semantics in potentially surprising ways. Mixing `yield_output` (workflow output) with `send_message` (edge routing) should remain explicit.

**Implementation:** Modified `_validate_edge_type_compatibility()` in `_validation.py` to fall back to `workflow_output_types` when `output_types` is empty:

```python
# Get output types from source executor
# First try send_message output types, then fall back to yield_output types
# This supports workflow composition where terminal executors (using yield_output)
# may be connected to downstream executors via add_workflow()
source_output_types = list(source_executor.output_types)
if not source_output_types:
    source_output_types = list(source_executor.workflow_output_types)
```

**Note for users:** When adding post-processing after a composed workflow's terminal executor (e.g., adding an `OutputFormatter` after `ConcurrentBuilder`), the terminal executor must use `send_message()` instead of `yield_output()` for the data to flow through the edge. This can be achieved with a custom aggregator:

```python
class ForwardingAggregator(Executor):
    @handler
    async def aggregate(
        self, results: list[AgentExecutorResponse], ctx: WorkflowContext[list[ChatMessage]]
    ) -> None:
        # Extract and forward messages (uses send_message, not yield_output)
        messages = [msg for r in results for msg in r.agent_response.messages if msg.role == Role.ASSISTANT]
        await ctx.send_message(messages)

# Use with ConcurrentBuilder
analysis = ConcurrentBuilder().participants([...]).with_aggregator(ForwardingAggregator())
```

---

## Implementation Phases

### Phase 1: Core `add_workflow()` ✅

1. Add internal `WorkflowMapping` dataclass (entry/exit tracking)
2. Add `_to_builder()` to ConcurrentBuilder and SequentialBuilder
3. Implement `add_workflow()` on WorkflowBuilder
4. Add logical ID resolution to `add_edge()` and `set_start_executor()`
5. Add tests for basic composition

### Phase 2: Type Validation ✅

1. ~~Add `_input_types` / `_output_types` properties to builders~~ (Using existing executor type introspection)
2. Enhance `build()` validation to check cross-workflow type compatibility (fall back to `workflow_output_types`)
3. Improve error messages

### Phase 3: Remaining Builders

1. Add `_to_builder()` to GroupChatBuilder, HandoffBuilder, MagenticBuilder
2. Support `Workflow` as input to `add_workflow()`
3. Documentation and examples
