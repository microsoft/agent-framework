# Durable hosting: multiple workflows and sub-workflows (Python)

Status: Implemented — decisions promoted to
[ADR-0030](../decisions/0030-durabletask-multiworkflow-and-subworkflows.md)
Scope: `python/packages/durabletask` (standalone Durable Task worker) and
`python/packages/azurefunctions` (Azure Functions host)
Related: PR #6418 (standalone Durable Task workflow hosting), core
`agent_framework._workflows`

This document sketches the work needed to add two capabilities to the Python
durable workflow hosting layer:

1. **Multiple workflows per host** — register and address more than one workflow
   on a single worker / Function App.
2. **Sub-workflows** — run a `Workflow` nested inside another workflow under
   durable execution.

It maps the current single-workflow architecture, summarizes the existing .NET
implementation and the in-process core engine, then proposes a design with
options, recommendations, and a phased work breakdown. Where the .NET approach
is shaped by C#/DI specifics, the Python-specific recommendation is called out.

---

## 1. Current state (single workflow)

The durable hosting layer today assumes exactly one workflow per host.

- **Fixed orchestrator name.** `WORKFLOW_ORCHESTRATOR_NAME = "workflow_orchestrator"`
  is a module constant in `_workflows/orchestrator.py`, exported from the package
  `__all__`. Every workflow registers and starts under this one name.
- **Singular worker registration.** `DurableAIAgentWorker.configure_workflow(workflow)`
  stores `self._workflow = workflow` and registers one orchestrator whose
  `__name__` is set to the fixed constant.
- **Registration planner.** `plan_workflow_registration(workflow)` walks
  `workflow.executors.values()` and classifies each executor: `AgentExecutor`
  becomes a durable **entity**, everything else becomes a durable **activity**.
  It returns a single `WorkflowRegistrationPlan(agent_executors, activity_executors,
  orchestrator_name)`.
- **Global durable names.** Activities and agent entities are named
  `dafx-{executor.id}` (`AgentSessionId.to_entity_name` uses the same `dafx-`
  prefix). These names are **global per task hub**, so two workflows sharing an
  executor id collide.
- **Singular client.** `DurableWorkflowClient.start_workflow()` (and
  `run_workflow` / `stream_workflow`) always schedule `WORKFLOW_ORCHESTRATOR_NAME`.
  There is no per-workflow targeting.
- **Singular Functions host.** `AgentFunctionApp(workflow=...)` takes one workflow,
  registers one orchestrator (`workflow_orchestrator`), per-executor activities
  (`dafx-{executor.id}`), and three flat HTTP routes: `workflow/run`,
  `workflow/status/{instanceId}`, `workflow/respond/{instanceId}/{requestId}`.
  The route-scoping check `_is_workflow_orchestration(status)` compares
  `status.name.casefold() == WORKFLOW_ORCHESTRATOR_NAME.casefold()` so a caller
  cannot read or inject into unrelated orchestrations in the same hub.

**No sub-workflow support exists.** Searching both packages for
`subworkflow` / `WorkflowExecutor` / `nested` returns nothing. A core
`WorkflowExecutor` (see §3) is not an `AgentExecutor`, so the planner currently
classifies it as a plain non-agent executor and would register it as a single
activity. Its activity body calls `executor.execute(...)`, which runs the
**entire inner workflow in-process inside one activity invocation** via
`WorkflowExecutor.process_workflow` → `self.workflow.run(...)`. That means:

- inner executors do not become durable activities/entities (no durable replay
  for inner steps, inner agent calls are not durable entity calls);
- inner human-in-the-loop (HITL) cannot pause — there is no external-event pump
  inside an activity, and the default `propagate_request=False` emits a
  `SubWorkflowRequestMessage` to a parent executor that the durable host never
  wires up;
- a long inner workflow can exceed activity time limits;
- inner events are not streamed.

So sub-workflows are effectively unsupported, not merely unoptimized.

---

## 2. .NET reference (alignment baseline)

The .NET hosting layer already supports both capabilities. Key facts to align
with (or deliberately diverge from):

- **Multiple workflows, keyed by name.** `AddWorkflow(name, factory)` registers
  workflows additively, keyed by `Workflow.Name` (lookup dictionary uses
  `StringComparer.OrdinalIgnoreCase`; registration asserts the factory's
  `Workflow.Name` matches the key).
- **Per-workflow orchestration name.** `WorkflowNamingHelper.ToOrchestrationFunctionName(name)`
  returns `"dafx-" + name`, with a `ToWorkflowName` reverse. The orchestration
  name is parameterized, not fixed.
- **Per-workflow HTTP routes.** `workflows/{workflowName}/run`,
  `workflows/{workflowName}/status/{runId}`, `workflows/{workflowName}/respond/{runId}`.
  Ownership is enforced by `IsOrchestrationOwnedByWorkflow(orchestrationName,
  functionName, suffix)` comparing the instance's orchestration name to
  `dafx-{routeWorkflowName}`.
- **Executor → durable mapping (in the durable host).** Non-agent executor →
  durable **activity** `dafx-{executorName}` (dispatched via
  `context.CallActivityAsync`, so results are cached in orchestration history and
  not re-run on replay); agent executor → durable **entity**
  `AgentSessionId.ToEntityName(executorName)`. So in the .NET *durable* host the
  executors are durable activities/entities — the same model Python uses — *not*
  in-process objects. The dispatch switch lives in `DurableExecutorDispatcher.DispatchAsync`.
  Activity registration is deduplicated across workflows by name via a `HashSet`,
  and the executor registry is keyed by executor name (first registration wins),
  so two workflows that define different executors with the same name **collide**
  (a documented constraint, not a fix).
- **Sub-workflows run as durable CHILD ORCHESTRATIONS (not in-process).** In the
  *durable* host, `DurableExecutorDispatcher.ExecuteSubWorkflowAsync` dispatches a
  sub-workflow node via `context.CallSubOrchestratorAsync("dafx-{innerName}", ...)`.
  The child orchestration runs the same superstep loop and its inner executors are
  durable activities/entities cached in the *child's* history. Sub-workflow and
  request-port bindings are skipped by activity registration precisely because
  they use this specialized dispatch. (The `WorkflowHostExecutor` /
  `InProcessRunner` path is the **core in-process engine**, a separate runtime; it
  is *not* how the durable host runs sub-workflows.)
- **Client retains workflow identity.** `IWorkflowClient.RunAsync(workflow, input, runId)`;
  run handles carry `WorkflowName`.

**Corrected mental model (resolving an earlier mistake in this doc):** in the
.NET *durable* host, non-agent executors are durable activities, agent executors
are durable entities, and sub-workflows are durable child orchestrations via
`CallSubOrchestratorAsync`. "Executors run in-process" is true only of the *core
in-process engine*, never the durable host. This means the Python child-
orchestration model for sub-workflows (see §5) is **alignment with .NET, not a
divergence**.

---

## 3. Core in-process model (what we mirror durably)

The core engine (`agent_framework._workflows`) already models nested workflows
in-process, and the durable layer should mirror its semantics:

- **`WorkflowExecutor(Executor)`** wraps a `Workflow` as an executor
  (`process_workflow` runs `self.workflow.run(input)`), publicly exported from
  `agent_framework` along with `SubWorkflowRequestMessage` /
  `SubWorkflowResponseMessage`.
- **Request bridging.** Inner `request_info` either propagates to the parent's
  own request surface (`propagate_request=True` → `ctx.request_info(...)`) or is
  wrapped as a `SubWorkflowRequestMessage` sent to a parent executor
  (`propagate_request=False`, the default). Responses route back by `request_id`.
- **Isolation + concurrency.** Each inner run gets an `execution_id`; a
  `request_id → execution_id` map routes responses to the correct concurrent run.
- **Checkpointing.** `on_checkpoint_save` / `on_checkpoint_restore` persist the
  inner execution contexts and rehydrate pending request-info events.
- **Execution + events.** Pregel-style supersteps; `WorkflowEvent` types include
  `output`, `intermediate`, `request_info`, `executor_invoked/completed`,
  `superstep_*`, lifecycle/diagnostic. `State` is shared within a workflow and
  isolated per workflow instance.

The durable orchestrator (`run_workflow_orchestrator`) already re-implements the
superstep loop, edge-group routing, fan-in/out, and HITL pause/resume against the
`WorkflowOrchestrationContext` protocol. Sub-workflow support extends this loop to
a new executor category; multi-workflow support parameterizes registration and
naming around it.

---

## 4. Part 1 — Multiple workflows per host

### 4.1 Naming helpers (foundation)

Replace the fixed constant with a helper pair, mirroring .NET
`WorkflowNamingHelper`:

```python
WORKFLOW_ORCHESTRATOR_PREFIX = "dafx-"

def workflow_orchestrator_name(workflow_name: str) -> str:  # "dafx-{name}"
def workflow_name_from_orchestrator(name: str) -> str | None  # reverse, validates prefix
def sanitize_workflow_name(name: str) -> str  # enforce durable-safe charset
```

Notes:
- This aligns the Python orchestration name scheme with .NET (`dafx-{name}`).
- `WORKFLOW_ORCHESTRATOR_NAME` stays exported as a **deprecated** alias to keep
  the public surface stable; see §6 back-compat.

### 4.2 Workflow names must be explicit and stable

`WorkflowBuilder` defaults an unnamed workflow to `f"WorkflowBuilder-{uuid4()}"`.
A random name regenerates on every process build, which would change the
orchestration function name across worker restarts and **break resume of
in-flight instances**. Therefore:

- Multi-workflow hosting **requires an explicit, stable `Workflow.name`** (reject
  auto-generated `WorkflowBuilder-<uuid>` names at registration, mirroring .NET's
  assert-name-matches-key contract).
- Names are validated/sanitized to the durable name charset.
- Duplicate names within one host are rejected.

### 4.3 Durable names (decision: scope workflow-internal names by workflow)

The orchestration name stays **`dafx-{workflowName}`** (matches .NET; this is the
name the Durable Task tooling/UI keys off). For a workflow's **internal**
executors and agents, the durable names are **scoped by workflow**:

- non-agent activity: `dafx-{workflowName}-{executorId}`
- agent entity: `dafx-{workflowName}-{executorId}`

Each workflow registers its own distinctly named activities/entities, each a
closure capturing that workflow's specific executor/agent instance (the same
shape as today's single-workflow code, just with a longer name). `(workflow,
executor)` is globally unique, so two co-hosted workflows that reuse an executor
id never collide.

**Why scope the names instead of resolving a bare name at runtime.** A
`dafx-{executorId}` activity/entity is created by a factory that **captures one
specific instance** (e.g. `__create_agent_entity` → `AgentEntity(agent=agent,
...)`, registered once via `add_entity`; `add_agent` even raises `ValueError` on
a duplicate id). With one global name per executor id, two workflows that define
the same id backed by **different** implementations (different agent
model/instructions/tools, or different executor code) would have one shadow the
other — a workflow silently gets behavior it did not expect. Putting the workflow
name in the durable name removes that foot-gun directly: different names, no
shared registration, plain closures, no per-call workflow lookup.

This diverges from .NET's *inner* activity/entity names (.NET keeps bare
`dafx-{executorName}` and resolves from a global registry keyed by name, which
keeps the collision as a documented constraint). The divergence is deliberate and
low-cost: the **orchestration** name — the one the DT UI surfaces — is identical
to .NET (`dafx-{workflowName}`); only the inner activity/entity names differ, and
no tooling depends on those strings.

**Agent state is still isolated by the entity key.** Independent of naming, an
agent entity is addressed by `(name, key)` with `key = ctx.instance_id`
(`_prepare_agent_task` → `AgentSessionId(name=..., key=instance_id)`), so two runs
never share conversation state and each run keeps its own session across turns —
mirroring core. Scoping the *name* fixes *which implementation* runs; the *key*
already isolated *state*.

**Agent addressing (decision).** Workflow agents stay reachable, just under a
**workflow-qualified** identity rather than a bare one. Both registration paths
funnel through the same primitive today — `AgentFunctionApp` calls
`add_agent(agent, entity_id=...)` for `agents=` *and* for each agent extracted
from a workflow, and `DurableAIAgentWorker` does the same in `configure_workflow`.
The only change is the name the planner hands to that primitive for workflow
agents: scoped `{workflowName}-{executorId}` instead of bare `executorId`. So:

- `agents=` (FunctionApp) / `add_agent(...)` (worker) → **bare** `dafx-{agentName}`,
  the standalone HTTP/MCP-addressable surface.
- agents inside a `workflow` → **scoped** `dafx-{workflowName}-{executorId}`,
  registered through the *same* primitive, still tracked in the registry.

Lookup is qualified, so workflow agents do **not** disappear from the surface:

```python
get_agent("translator")                          # bare standalone agent
get_agent("translator", workflow_name="orders")  # workflow-scoped agent
```

We deliberately do **not** add a `workflow_agents=` constructor input. The agents
already live inside the `Workflow` object (each `AgentExecutor` holds its agent),
so a separate map would duplicate that and create a source-of-truth conflict. The
per-workflow agent grouping `{workflow_name: [agent_executors]}` is an *internal*
structure the planner produces and both hosts consume — not a public kwarg. An
agent used both standalone and inside a workflow is registered both ways and
becomes two independent entities (bare + scoped) with separate state, which is the
intended separation. This keeps "workflow step vs standalone callable" an explicit
registration choice while keeping both reachable.

*Cross-workflow shared* agent memory (one agent that deliberately remembers
across two co-hosted workflows) remains out of scope; it would need an explicit
stable shared entity key rather than `instance_id`.

### 4.4 Standalone worker changes (`durabletask`)

- `DurableAIAgentWorker.configure_workflow` becomes **additive**: store
  `self._workflows: dict[str, Workflow]` keyed by sanitized name; reject
  duplicates and auto-generated names.
- Register one orchestrator per workflow, each a closure capturing its `Workflow`,
  with `__name__ = workflow_orchestrator_name(name)`.
- Register that workflow's non-agent activities and agent entities under their
  **scoped** names `dafx-{workflowName}-{executorId}` (§4.3), each capturing the
  specific executor/agent instance, via the **same** `add_agent` /
  activity-registration primitives that standalone `add_agent` uses (only the
  name differs). Workflow agents stay tracked in the registry under their
  workflow-qualified identity; an agent that should *also* be standalone-
  addressable under a bare name is registered separately via `add_agent`.
- `plan_workflow_registration` already returns `orchestrator_name`; extend it to
  also group agents/activities per workflow and thread the per-workflow name
  through it (the `{workflow_name: [...]}` grouping both hosts consume).

### 4.5 Client changes (`DurableWorkflowClient`)

- Add an optional `workflow_name` to `start_workflow` / `run_workflow` /
  `stream_workflow`. The client resolves the orchestration name via
  `workflow_orchestrator_name(workflow_name)`.
- When the worker hosts exactly one workflow, `workflow_name` may be omitted
  (resolves to the sole registered workflow) for ergonomic back-compat.
- Status/HITL methods remain keyed by `instance_id`; add an optional
  `workflow_name` used to validate ownership (the instance's orchestration name
  must match), mirroring `_is_workflow_orchestration`.

### 4.6 Azure Functions host changes (`azurefunctions`)

- `AgentFunctionApp` accepts `workflows: list[Workflow] | dict[str, Workflow]`
  (keep singular `workflow=` as a back-compat alias for one entry).
- Per workflow: register an orchestrator via
  `@function_name(workflow_orchestrator_name(name))` + `@orchestration_trigger`,
  register its activities/entities under scoped names
  `dafx-{workflowName}-{executorId}` (§4.3), and register **per-workflow routes**:
  `workflow/{workflowName}/run`, `workflow/{workflowName}/status/{instanceId}`,
  `workflow/{workflowName}/respond/{instanceId}/{requestId}`.
- **Routes are always per-workflow, even for a single workflow** (decision §8).
  Keeping the shape constant means downstream callers do not have to change URLs
  when an app grows from one workflow to many — the single-workflow case is just
  the one-element case of the general shape. (No legacy flat `workflow/run`
  aliases; this is still a preview surface.)
- Replace `_is_workflow_orchestration(status)` with
  `_is_owned_orchestration(status, workflow_name)` comparing
  `status.name == workflow_orchestrator_name(workflow_name)` (the existing
  case-insensitive comment already anticipated per-workflow names).
- Workflow agents register through the **same** `add_agent` primitive as
  `agents=`, under the scoped name `dafx-{workflowName}-{executorId}`, so they
  stay tracked in the registry. `get_agent` gains an optional `workflow_name` to
  resolve them: `get_agent(name)` for bare standalone agents,
  `get_agent(name, workflow_name=...)` for workflow-scoped agents. Expose an agent
  standalone (bare `dafx-{agentName}`) by passing it via `agents=`; an agent used
  both ways is registered both ways and yields two independent entities (§4.3).
- No `workflow_agents=` constructor kwarg — the agents already live inside each
  `Workflow`; the per-workflow grouping is internal (§4.3).

---

## 5. Part 2 — Sub-workflows

A `WorkflowExecutor` node in a hosted workflow must run its inner `Workflow`
durably. Three execution models were considered.

### 5.1 Models considered

- **Model A — inner workflow inside one activity (status quo).** Register the
  `WorkflowExecutor` as a normal activity; its body runs `inner.workflow.run()`
  in-process. Simplest, but not durable, cannot pause for inner HITL, and risks
  activity timeouts. **Rejected** as the primary model (it is today's accidental,
  broken behavior).
- **Model B — child orchestration (recommended).** When the orchestrator reaches
  a `WorkflowExecutor` node, it starts the inner workflow as a **durable child
  orchestration** (`call_sub_orchestrator(workflow_orchestrator_name(inner_name),
  input=...)`) and awaits its result like any other task. The inner workflow's
  executors become its own activities/entities; it is independently durable,
  checkpointed, observable (own instance id), and can run long without hitting
  activity limits.
- **Model C — inlined supersteps.** Recursively drive the inner workflow's
  superstep loop inside the parent orchestration generator, scheduling inner
  executor activities directly and qualifying inner request ids
  (`{subId}.{requestId}`) like .NET ports. Durable and single-instance, but
  bloats one orchestration history, prevents independent inner observation, and
  re-implements nesting bookkeeping in the generator. **Rejected** as primary
  (highest complexity, weakest observability).

### 5.2 Recommendation: Model B (child orchestration)

Model B is the natural durable fit for Python because Python's executors already
run as activities/entities driven by the orchestrator — so a sub-workflow is just
**another registered workflow started by a parent instead of by HTTP**. It reuses
the entire Part 1 multi-workflow machinery (named registration, per-workflow
orchestrator, scoped activity/entity names, ownership checks).

**This matches .NET.** The .NET *durable* host dispatches sub-workflow nodes via
`DurableExecutorDispatcher.ExecuteSubWorkflowAsync` →
`context.CallSubOrchestratorAsync("dafx-{innerName}", ...)`, and the child
orchestration runs its own superstep loop with its inner executors as durable
activities/entities in the child's history. Model B is the same approach in
Python (the `WorkflowHostExecutor` / `InProcessRunner` path is the *core in-
process engine*, not the durable host). The tradeoff is more orchestration
instances (extra bookkeeping and more rows in the DT UI) in exchange for true
inner durability, independent inner observability, inner HITL, and no activity-
timeout coupling.

### 5.3 Required changes

- **Protocol.** Add `call_sub_orchestrator(name, input, instance_id=None)` to the
  `WorkflowOrchestrationContext` protocol, implemented by both adapters
  (`DurableTaskWorkflowContext` → `OrchestrationContext.call_sub_orchestrator`;
  `AzureFunctionsWorkflowContext` → `DurableOrchestrationContext.call_sub_orchestrator`).
  Both underlying SDKs support sub-orchestrations.
- **Planner.** Extend `plan_workflow_registration` to detect
  `isinstance(executor, WorkflowExecutor)` and return a new
  `subworkflow_executors` category carrying the inner `Workflow`. The host then
  (a) **recursively registers** the inner workflow's orchestrator/activities/
  entities, and (b) does **not** register the `WorkflowExecutor` itself as an
  activity.
- **Orchestrator routing.** In `run_workflow_orchestrator`'s task-preparation
  phase, route a message destined for a `WorkflowExecutor` node to
  `ctx.call_sub_orchestrator(...)` instead of an activity task. The child's
  result feeds back into edge routing exactly like an activity result (outputs →
  messages / final outputs).
- **Deterministic child instance ids.** Derive
  `f"{parent_instance_id}::{executor_id}"` (append a deterministic counter when a
  `WorkflowExecutor` runs on multiple messages in a superstep, e.g. fan-out) for
  discoverability and idempotent replay.
- **Recursion bound.** Detect cycles and cap nesting depth (configurable) to
  prevent unbounded sub-orchestration trees.
- **Result/output mapping.** Reuse the existing typed-output reconstruction
  (`deserialize_workflow_output`) on the child result before routing.

### 5.4 Sub-workflow HITL

The inner workflow's `request_info` surfaces in the **child** orchestration's
custom status. Two addressing options:

- **B1 — direct child addressing.** Expose child instance ids; the responder
  posts to `workflow/{innerName}/respond/{childInstanceId}/{requestId}`. Simple;
  caller discovers child ids from the parent status (which lists nested pending
  requests with their child instance ids).
- **B2 — propagated single surface (recommended, .NET-aligned philosophy).**
  Bubble inner pending requests up into the **parent** custom status with
  **qualified request ids** (`{executor_path}::{requestId}`), mirroring .NET port
  qualification. A response to the parent is routed by stripping the qualifier and
  raising the event on the owning child instance. One addressing surface for
  arbitrarily deep nesting, at the cost of parent→child response plumbing.

**Decision: B2 (propagated single surface).** Pending inner requests bubble up
into the **parent** custom status with **qualified request ids**
(`{executor_path}::{requestId}`), mirroring .NET port qualification. A response to
the parent is routed by stripping the qualifier and raising the event on the
owning child instance. This gives one addressing surface for arbitrarily deep
nesting (the caller always talks to the top-level run), at the cost of
parent→child response plumbing. It is consistent with the "always per-workflow,
stable surface" routing decision: callers never need to discover child instance
ids. B1 (direct child addressing) is the rejected alternative — simpler plumbing
but leaks child instance ids into the caller and changes the surface per nesting
depth.

---

## 6. Cross-cutting concerns

- **Back-compat / migration (decision: hard switch).** `WORKFLOW_ORCHESTRATOR_NAME`
  stays exported as a deprecated alias for source compatibility, but the
  single-workflow default orchestration name moves from `workflow_orchestrator`
  to `dafx-{name}` with **no runtime alias**. This means **in-flight
  single-workflow instances created before the upgrade will not resume** under
  the new name. Accepted because durable workflow runs are typically short-lived
  and this is a preview surface; operators should drain in-flight workflow
  instances before upgrading. (Resolves former open decision; §8.)
- **Determinism.** `call_sub_orchestrator`, `wait_for_external_event`, and timers
  are replay-safe; child instance ids must be derived deterministically (no
  `uuid4()` in the orchestrator — use `ctx.new_uuid()` or derived ids).
- **Security / route scoping.** Per-workflow ownership checks
  (`_is_owned_orchestration`) extend the existing defense so a caller holding an
  instance id cannot cross workflow boundaries. Sub-workflow respond endpoints
  validate child ownership the same way.
- **Streaming.** `supports_event_streaming` stays host-gated (Azure Functions
  off due to the 16 KB custom-status cap). Nested event propagation respects the
  same gate.

---

## 7. Phased work breakdown

Each phase is independently shippable.

- **Phase 0 — naming + validation.** Add `workflow_orchestrator_name` /
  reverse / `sanitize_workflow_name`; deprecate `WORKFLOW_ORCHESTRATOR_NAME`.
  Unit tests for naming round-trips and validation. (durabletask)
- **Phase 1 — multiple workflows on the standalone worker.** Additive
  `configure_workflow`, per-workflow orchestrators, scoped activity/entity names
  `dafx-{workflowName}-{executorId}`, client `workflow_name` targeting +
  ownership. Unit + integration tests with two workflows in one hub (including two
  workflows that reuse an executor/agent id with different implementations).
- **Phase 2 — multiple workflows on Azure Functions.** `workflows=`,
  per-workflow orchestrators/activities/routes (always per-workflow),
  `_is_owned_orchestration`. Unit tests + a two-workflow sample.
- **Phase 3 — sub-workflows via child orchestrations.** Protocol
  `call_sub_orchestrator` + both adapters; planner `subworkflow_executors` +
  recursive registration; orchestrator routing; deterministic child ids;
  recursion bound. Unit + integration tests + a nested-workflow sample.
- **Phase 4 — sub-workflow HITL (B2).** Propagate inner pending requests to the
  parent custom status with qualified request ids; route a parent response to the
  owning child instance by stripping the qualifier. Tests + HITL sub-workflow
  sample.
- **Phase 5 — docs, samples, ADR(s).** Promote the multi-workflow and
  sub-workflow decisions into ADR(s) under `docs/decisions/`; add README/runbook
  updates.

---

## 8. Decisions

**Resolved:**

1. **Orchestration naming** (§4.1, §4.3): orchestration name **`dafx-{workflowName}`**
   (matches .NET; the name the Durable Task tooling/UI surfaces).
2. **Workflow-internal durable names** (§4.3): scope inner activity/entity names
   by workflow — **`dafx-{workflowName}-{executorId}`** (Approach A). Distinct
   names per workflow, plain closures, no runtime registry; removes the
   same-executor-id collision. Diverges from .NET's bare inner names, but only the
   orchestration name (identical to .NET) is UI-surfaced.
3. **Multi-workflow route shape on Azure Functions** (§4.6): **always per-workflow
   routes**, so downstream callers don't change URLs when an app grows from one
   workflow to many.
4. **Sub-workflow execution model** (§5): **Model B (child orchestration via
   `call_sub_orchestrator`)**, which is what the .NET durable host does
   (`ExecuteSubWorkflowAsync`). Accept more orchestration instances in exchange
   for inner durability and observability.
5. **Single-workflow orchestration-name migration** (§6): **hard switch** to
   `dafx-{name}` with no runtime alias. Pre-upgrade in-flight instances under
   `workflow_orchestrator` won't resume; acceptable for a preview surface.
6. **Sub-workflow HITL addressing** (§5.4): **B2** — propagate inner pending
   requests to the parent custom status with qualified request ids; the caller
   always responds to the top-level run.
7. **Agent addressing** (§4.3, §4.6): workflow agents register through the **same**
   `add_agent` primitive as `agents=`, under the scoped name
   `dafx-{workflowName}-{executorId}`, and stay reachable via
   `get_agent(name, workflow_name=...)`. Bare `agents=` registration keeps the
   standalone `dafx-{agentName}` surface. No `workflow_agents=` kwarg — the
   per-workflow grouping is an internal planner structure both hosts consume.
   Agent conversation *state* stays isolated by the entity key (`ctx.instance_id`)
   regardless of naming.

**Still open:**

- **Cross-workflow shared agents** (§4.3): a single agent that intentionally
  shares conversation memory across two co-hosted workflows is out of scope; if
  wanted later it needs an explicit stable shared entity key rather than
  `instance_id`. Flagged as a possible follow-up, not part of this work.
