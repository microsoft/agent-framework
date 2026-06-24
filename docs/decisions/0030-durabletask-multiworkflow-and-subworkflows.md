---
status: proposed
contact: ahmedmuhsin
date: 2025-06-13
deciders: ahmedmuhsin
consulted:
informed:
---

# Durable Task hosting: multiple workflows per host and sub-workflows

## Context and Problem Statement

The Python Durable Task hosting layer (the standalone `DurableAIAgentWorker` and the Azure Functions `AgentFunctionApp`) originally hosted exactly **one** MAF `Workflow` per host, registered under a single fixed orchestration name (`workflow_orchestrator`). Two capabilities were missing relative to the in-process MAF runtime and the .NET durable host:

1. **Multiple workflows per host** — one worker / one Function app could not host more than one workflow, and two workflows that happened to reuse an executor or agent id would collide on shared durable primitive names.
2. **Sub-workflows (composition)** — MAF's `WorkflowExecutor` embeds one workflow inside another, but the durable hosts had no way to run a nested workflow as a first-class durable unit.

This ADR records the design decisions for adding both capabilities to the Python durable hosts, keeping them aligned with the .NET durable host where it matters (the Durable Task tooling/UI surface) and with the in-process MAF semantics everywhere else. The full design exploration lives in [`docs/design/durabletask-multiworkflow-and-subworkflows.md`](../design/durabletask-multiworkflow-and-subworkflows.md); this ADR captures the decisions and the considered alternatives.

## Decision Drivers

- **Stable durable identities.** Durable replay only resumes an in-flight orchestration if the orchestration/activity/entity names still resolve to the same functions. Names must be stable across restarts and derived deterministically from a workflow name.
- **No accidental collisions.** Two co-hosted workflows that reuse an executor or agent id must not share a durable entity/activity, or one workflow's implementation would silently service another's dispatch.
- **Alignment with .NET on the surfaced identity.** The orchestration name is what the Durable Task tooling/UI shows; it should match .NET's `WorkflowNamingHelper` byte-for-byte.
- **Alignment with in-process MAF semantics.** Sub-workflow output forwarding, HITL request/response, and per-run state isolation should behave the same durably as in-process.
- **Stable caller surface.** HTTP callers should not have to change URLs as an app grows from one workflow to many, or discover internal child orchestration instance ids for nested HITL.
- **Determinism.** Orchestrator code must be replay-safe (deterministic child instance ids, no `uuid4()` in the orchestrator).

## Considered Options

The design has several semi-independent decision points; the considered alternatives are grouped by decision below. The chosen options are summarized in the Decision Outcome.

### Workflow-internal durable names (collision avoidance)

- **Approach A — scope inner names by workflow** (`dafx-{workflowName}-{executorId}`). Distinct names per workflow using plain closures; no runtime registry.
  - Good: removes same-executor-id collisions with no extra moving parts.
  - Good: each workflow's primitives are independently inspectable.
  - Neutral: diverges from .NET's bare `dafx-{executorId}` inner names (but those are not UI-surfaced).
- **Approach B — a runtime registry keyed by (workflow, executor)** mapping to shared handlers.
  - Good: closer to .NET's bare inner names.
  - Bad: introduces a registry indirection and a stateful lookup on the hot path; more to get wrong on replay.

### Sub-workflow execution model

- **Model A — run the inner workflow inside one activity** of the parent orchestration.
  - Good: fewest orchestration instances.
  - Bad: the inner workflow's executors are not independently durable or observable; HITL inside the inner workflow cannot pause durably.
- **Model B — run the inner workflow as a durable child orchestration** via `call_sub_orchestrator(dafx-{innerName})`.
  - Good: matches what the .NET durable host does (`ExecuteSubWorkflowAsync` → child orchestration).
  - Good: inner executors are independently durable/observable; inner HITL pauses durably on the child instance.
  - Neutral: more orchestration instances on the task hub.

### Azure Functions route shape for multiple workflows

- **Always per-workflow routes** (`workflow/{name}/run|status|respond`), even for a single workflow.
  - Good: the URL shape never changes as an app grows; callers are stable.
  - Neutral: a single-workflow app has a slightly longer URL.
- **Bare routes for one workflow, per-workflow routes only when there are many.**
  - Bad: callers must change URLs when a second workflow is added.

### Single-workflow orchestration-name migration

- **Hard switch** to `dafx-{name}` with no runtime alias for the old `workflow_orchestrator` name.
  - Good: one naming scheme everywhere; no special-case alias code.
  - Bad: pre-upgrade in-flight single-workflow instances under `workflow_orchestrator` will not resume.
  - Acceptable: durable workflow runs are typically short-lived and this is a preview surface; operators drain in-flight instances before upgrading. `WORKFLOW_ORCHESTRATOR_NAME` remains exported as a deprecated source alias.
- **Dual registration / runtime alias** that resumes both names.
  - Good: in-flight instances survive the upgrade.
  - Bad: permanent alias-compat code on a preview surface for a low-value case.

### Sub-workflow HITL addressing

- **B1 — direct child addressing.** Expose child instance ids; the responder posts to `workflow/{innerName}/respond/{childInstanceId}/{requestId}`.
  - Good: simple host plumbing.
  - Bad: leaks child instance ids to the caller and changes the addressing surface per nesting depth.
- **B2 — propagated single surface.** Bubble inner pending requests up into the parent custom status with qualified request ids (`{executorId}~{ordinal}~{requestId}`); a response to the parent is routed by peeling one hop and raising the event on the owning child instance.
  - Good: one addressing surface for arbitrarily deep nesting; the caller always talks to the top-level run.
  - Good: consistent with the "always per-workflow, stable surface" decision.
  - Good: the `~{ordinal}~` hop indexes the parent's `subworkflows` child list, so a node that dispatches several children in one superstep keeps each addressable.
  - Neutral: requires parent→child response plumbing in the host/client.
  - Note: the separator is `~` (not `::`) because core emits `auto::{index}` request ids for functional `@workflow` HITL; `~` never appears in a core request id and is rejected in executor ids, so qualified ids round-trip unambiguously.

### Workflow agent addressing

- **Reuse `add_agent` with a scoped entity id** (`dafx-{workflowName}-{executorId}`); workflow agents are reachable via `get_agent(name, workflow_name=...)`. No separate `workflow_agents=` kwarg.
  - Good: one registration path; workflow agents appear in `agents` / `get_agent`.
  - Good: the per-workflow grouping is an internal planner structure both hosts consume.
- **A separate `workflow_agents=` registration surface.**
  - Bad: a parallel registration path and a second public kwarg for what is an internal grouping concern.

## Decision Outcome

1. **Orchestration naming:** `dafx-{workflowName}` (matches .NET; the UI-surfaced name).
2. **Workflow-internal durable names:** **Approach A** — scope inner activity/entity names by workflow (`dafx-{workflowName}-{executorId}`).
3. **Azure Functions route shape:** **always per-workflow routes** (`workflow/{name}/run|status|respond`).
4. **Sub-workflow execution model:** **Model B** — child orchestration via `call_sub_orchestrator`, matching the .NET durable host.
5. **Single-workflow migration:** **hard switch** to `dafx-{name}` with no runtime alias; `WORKFLOW_ORCHESTRATOR_NAME` stays as a deprecated source alias only.
6. **Sub-workflow HITL addressing:** **B2** — propagate inner pending requests to the parent custom status with qualified request ids (`{executorId}~{ordinal}~{requestId}`); the caller always responds to the top-level run.
7. **Workflow agent addressing:** register through the **same** `add_agent` primitive under the scoped name; reachable via `get_agent(name, workflow_name=...)`; no `workflow_agents=` kwarg. Agent conversation state stays isolated by the entity key (`ctx.instance_id`).
8. **Hardening:** reject two **different** workflow instances that share a name (the same instance reused by several nodes is deduped); validate executor ids (separator-free, length-bounded); and strip the reserved sub-workflow envelope key from untrusted client input at the host boundary so a forged envelope cannot reach the trusted pickle path. Sub-workflow nesting is **not** capped by a depth counter — the nesting tree is finite at build time and the durable instance-id length limit is the natural ceiling (matching .NET, which imposes no limit).

### Consequences

- Good: two workflows can be co-hosted on one worker / app and reuse executor and agent ids without colliding; each workflow's durable primitives are independently inspectable.
- Good: sub-workflows are first-class durable units; inner HITL pauses durably and surfaces behind a single top-level addressing surface.
- Good: the orchestration name remains identical to .NET, so the Durable Task tooling/UI is consistent across languages.
- Good: HTTP callers have a stable URL shape and never need to discover internal child instance ids.
- Bad / accepted: pre-upgrade single-workflow instances under `workflow_orchestrator` will not resume after the hard switch.
- Neutral: sub-workflows add orchestration instances to the task hub (one child orchestration per `WorkflowExecutor` invocation).

### Out of scope / follow-up

- **Cross-workflow shared agents.** A single agent that intentionally shares conversation memory across two co-hosted workflows is out of scope. Today, agent state is isolated per run by the entity key (`ctx.instance_id`); intentional sharing would need an explicit stable shared entity key rather than `instance_id`. Flagged as a possible follow-up.

## More Information

- Design document: [`docs/design/durabletask-multiworkflow-and-subworkflows.md`](../design/durabletask-multiworkflow-and-subworkflows.md)
- Implementation: Python `agent_framework_durabletask` (standalone worker, client, orchestrator, naming) and `agent_framework_azurefunctions` (`AgentFunctionApp`).
- Samples: `python/samples/04-hosting/durabletask/11_subworkflow` (composition) and `.../12_subworkflow_hitl` (HITL inside a sub-workflow).
- .NET reference: `WorkflowNamingHelper` (orchestration naming) and the durable host's `ExecuteSubWorkflowAsync` (sub-workflow as child orchestration).
