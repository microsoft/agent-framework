# Microsoft.Agents.AI.Workflows

This package contains the core **workflow runtime** for the Microsoft Agent Framework [.NET SDK](../../README.md).
It provides graph-based orchestration with support for:

- **Executors and edges** connecting deterministic functions and agents
- **Streaming runs** over OpenAI-compatible events
- **Checkpointing and resume** for long-running workflows
- **Human-in-the-loop (HITL)** approval and request/response steps
- **Observability** via OpenTelemetry and structured workflow events

> If you are new to Agent Framework workflows, start with the samples under
> [`dotnet/samples/03-workflows`](../../samples/03-workflows/) before building
> your own workflows.

---

## Key concepts

- **Workflow graph**
  - A workflow is defined as a **graph** of executors (nodes) and edges (links).
  - The graph is built using `WorkflowBuilder`, `AgentWorkflowBuilder`, or
    related builder types in this package.

- **Executors**
  - Executors are the units of work in a workflow: they can wrap agents,
    deterministic functions, or external services.
  - Core abstractions live in:
    - `Executor`, `StatefulExecutor`, and `FunctionExecutor`
    - `ExecutorBinding`, `ConfiguredExecutorBinding`, and related binding helpers

- **Edges and ports**
  - Edges model how data and control flow between executors.
  - Different edge types (direct, fan-out/fan-in, conditional, etc.) are
    represented via types under the `Execution` and `Checkpointing` namespaces.

- **Runs and sessions**
  - A **run** represents a single execution of a workflow.
  - A **workflow session** groups runs together and provides a place to store
    checkpoints and conversation history. This is what DevUI surfaces as
    “checkpoint storage”.

- **Checkpointing**
  - Checkpoints capture workflow state so that execution can be resumed later.
  - Types under the `Checkpointing` namespace (for example `Checkpoint`,
    `CheckpointInfo`, and `CheckpointManager`) implement this behavior.
  - Checkpoints can be stored using different providers (for example the Cosmos
    checkpoint store in `Microsoft.Agents.AI.CosmosNoSql`).

- **Events and observability**
  - Workflow execution emits rich events such as `WorkflowEvent`,
    `ExecutorEvent`, and `WorkflowOutputEvent`.
  - `Observability/WorkflowTelemetryOptions` and the `OpenTelemetryWorkflowBuilderExtensions`
    helpers let you integrate with OpenTelemetry tracing.

---

## Relationship to other packages

This package is designed to be used together with a few closely related packages:

- [`Microsoft.Agents.AI.Workflows.Declarative`](../Microsoft.Agents.AI.Workflows.Declarative/)
  - Adds **declarative (YAML-based) workflows** and integration with Power Fx.
  - Use this when you want to author workflows in configuration files instead
    of C#.

- [`Microsoft.Agents.AI.DurableTask`](../Microsoft.Agents.AI.DurableTask/)
  - Bridges workflows to **Durable Task** and durable agents.
  - Provides implementations for long-running, reliable workflows with external
    state storage.

- [`Microsoft.Agents.AI.Hosting`](../Microsoft.Agents.AI.Hosting/) and
  [`Microsoft.Agents.AI.DevUI`](../Microsoft.Agents.AI.DevUI/)
  - Provide hosting and developer experience around workflows:
    - HTTP endpoints and service registration
    - DevUI visualizations, execution timeline, and checkpoint browsing

You can use `Microsoft.Agents.AI.Workflows` on its own for in-process workflows,
or combine it with the packages above for hosting, durability, and visual tooling.

---

## Quick start (samples)

The fastest way to learn the workflows API is to explore the samples under
[`dotnet/samples/03-workflows`](../../samples/03-workflows/):

- **Getting started**: `_StartHere/*`
  - `01_Streaming` — basic streaming workflow with a small graph
  - `02_AgentsInWorkflows` — combining agents with executors
  - `05_SubWorkflows` — composing workflows from sub-workflows

- **Control flow and parallelism**
  - `ConditionalEdges/*` — edge conditions, switch cases, and multi-selection
  - `Concurrent/*` and `Loop` — concurrent runs, map-reduce, and loops

- **Checkpointing and resume**
  - `Checkpoint/*` — saving and resuming workflows, including HITL scenarios

- **Declarative workflows**
  - `Declarative/*` — YAML-based workflows that run on top of this package

Each sample shows a complete `Program.cs` that configures agents, builds a
workflow graph, and runs it using the types defined in this package.

---

## When to use workflows

Use `Microsoft.Agents.AI.Workflows` when:

- You need more than a single request/response style agent call.
- You want to compose multiple agents and deterministic steps into a **graph**.
- You care about **streaming**, **checkpointing**, or **HITL** during execution.
- You need strong observability and the ability to inspect the execution path.

For simple, single-agent flows, the base agent APIs may be sufficient. When the
interaction naturally forms a graph with multiple steps, workflows are the
recommended abstraction.


