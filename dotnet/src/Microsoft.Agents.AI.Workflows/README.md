## Microsoft.Agents.AI.Workflows

This package contains the core **workflow engine** for the Agent Framework .NET
stack. It provides the primitives used by the `dotnet/samples/03-workflows/`
samples to build, execute, and observe AI-centric workflows.

The goal of the library is to make it easy to:

- Model complex, multi-step processes as **typed workflows**
- Orchestrate **AI agents, tools, and services** as first-class executors
- Capture **events, telemetry, and checkpoints** for monitoring and diagnosis
- Host workflows alongside existing agents and applications

For concrete usage examples, see the samples in
`dotnet/samples/03-workflows/README.md`.

### Core concepts

- **Workflow**: A compiled, executable graph of steps (executors) and edges.
- **Executor**: A unit of work that takes an input payload and produces an
  output payload or event. Executors can wrap AI agents, tools, or arbitrary
  application logic.
- **Edges**: Connections between executors that define the control-flow
  (including conditional routing, fan-out/fan-in, loops, and sub-workflows).
- **Run**: A single execution of a workflow. Runs expose status, events, and
  checkpoints as they progress.
- **Ports / Requests**: Typed channels used to send messages into a workflow
  and receive responses or notifications (for example request/response style
  patterns or human-in-the-loop prompts).

### Important types

The following types live in this assembly (names may evolve as the library
iterates, but the roles stay the same):

- `Workflow` and `WorkflowBuilder` – build and configure executable workflows.
- `Run` and related events (`WorkflowStartedEvent`, `WorkflowOutputEvent`,
  `WorkflowWarningEvent`, `WorkflowErrorEvent`, etc.) – represent the lifecycle
  of an execution and surface progress to callers.
- `RequestPort`, `RequestPortBinding`, and related types – provide a structured
  way to send requests into a running workflow and receive replies.
- Specialized executors under `Specialized/` – pre-built building blocks for
  common patterns such as agent orchestration, group chat, and streaming.
- Checkpointing types under `Checkpointing/` – support saving and resuming
  workflow state.
- Observability types under `Observability/` – surface metrics and traces for
  workflows using .NET diagnostics and OpenTelemetry.

You typically do not construct these types directly in application code.
Instead, you use higher-level helpers in the samples, or abstractions like
`WorkflowHostAgent`, which wraps workflows so they can be driven via the
standard agent interfaces.

### Hosting and integration

The `WorkflowHostingExtensions` class contains the primary extension methods
for wiring workflows into hosting layers (for example ASP.NET or durable
agents). These helpers:

- Register the workflow engine in the dependency injection container
- Configure telemetry and logging for runs
- Expose workflows through agent hosts or durable task orchestrations

For recommended hosting patterns and end-to-end setups, prefer studying the
samples under:

- `dotnet/samples/03-workflows/` – workflow patterns and building blocks
- `dotnet/samples/04-hosting/` and `dotnet/samples/05-end-to-end/` – how
  workflows fit into larger applications

### Relationship to Declarative Workflows

The **Declarative Workflows** package (`dotnet/src/Microsoft.Agents.AI.Workflows.Declarative`)
builds on top of this core engine. Declarative workflows:

- Use YAML/JSON definitions instead of C# to describe workflows
- Rely on this library for execution, events, and telemetry
- Are demonstrated by the samples in `dotnet/samples/03-workflows/Declarative`

If you are authoring workflows in C#, you will primarily touch this package.
If you are building low-code / configuration-driven workflows, you will
primarily use the declarative package, which depends on this one.

