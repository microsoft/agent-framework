# Workflow and orchestration builder

Use a workflow when execution order, routing, parallelism, multiple participants, checkpoints, human input, or
intermediate outputs are part of the product contract.

## Choose the workflow API

| Need | API |
| --- | --- |
| Explicit typed graph and routing | `WorkflowBuilder` with `Executor` types or bound functions |
| Standard multi-agent collaboration | `AgentWorkflowBuilder` (`BuildSequential`, `BuildConcurrent`, handoff, group chat, Magentic) |
| Agent as a workflow stage | Bind an `AIAgent` into the graph as an executor |
| Workflow as an agent | `AsAIAgent(...)` from `WorkflowHostingExtensions` |
| YAML-defined actions and routing | `Microsoft.Agents.AI.Workflows.Declarative`; read [declarative.md](declarative.md) |

Package: `Microsoft.Agents.AI.Workflows`. Read
[workflow concepts](https://learn.microsoft.com/agent-framework/concepts/workflows/) and the XML docs for signatures
and execution options.

## Stable design rules

- Build the workflow once with `WorkflowBuilder` (`Build()`), then run it with `InProcessExecution` in streaming or
  non-streaming form. A built `Workflow` is the definition; each run owns its own execution state.
- Build fresh workflows when executors or wrapped agents hold run-specific state.
- Use the standard sequential, concurrent, handoff, group-chat, or Magentic builders before recreating those patterns.
- Define the message types flowing between executors explicitly; edges route by message type, so type changes are
  breaking changes to the graph.
- Select caller-facing output separately from intermediate progress. Executors yield output explicitly; workflow
  streams also carry framework events (executor invoked/completed/failed, superstep and request events).
- Wrap a workflow as an agent only when callers require the agent contract. Prefer native workflow hosting when the
  host supports it.
- Prefer `[MessageHandler]`-attributed executors with the source generator
  (`Microsoft.Agents.AI.Workflows.Generators`) where the current samples do; otherwise follow the current executor
  sample patterns.

## Agent-to-workflow migration

Before splitting an agent into stages, record its input, response, tools, middleware, context, session, and hosting
contract. Split responsibilities only where the topology changes correctness or observability. Define the messages
between stages, final output, intermediate output, session ownership, and approval behavior explicitly.

## Gotchas

- Checkpoint resume (`CheckpointManager`) requires stable workflow, executor, and participant IDs and serializable
  state and message types.
- Keep run-specific state in the workflow state APIs, not in fields shared across runs.
- Agent sessions are not automatically interchangeable between participants.
- Tool approval (`ToolApprovalRequestContent`) and workflow human input (`RequestPort` external requests) are
  different suspension mechanisms.
- Agents hosted as executors react to a `TurnToken` trigger after receiving messages; use the builder helpers or
  samples so participants actually start processing.
- Handoff and group-chat patterns transform conversation history between participants; verify what each participant
  sees.

## Validation

Exercise every route with deterministic executors first. Test final and intermediate outputs separately, then test
streaming, suspension/resume, participant sessions, approvals, and error propagation where used.

## Learn more

- [Workflow concepts](https://learn.microsoft.com/agent-framework/concepts/workflows/)
- [First workflow sample](https://github.com/microsoft/agent-framework/tree/main/dotnet/samples/01-get-started/05_first_workflow)
- [Workflow samples](https://github.com/microsoft/agent-framework/tree/main/dotnet/samples/03-workflows)
- [Agent orchestration patterns](https://github.com/microsoft/agent-framework/tree/main/dotnet/samples/03-workflows/_StartHere/03_AgentWorkflowPatterns)
- [Checkpoint samples](https://github.com/microsoft/agent-framework/tree/main/dotnet/samples/03-workflows/Checkpoint)
- [Human-in-the-loop samples](https://github.com/microsoft/agent-framework/tree/main/dotnet/samples/03-workflows/HumanInTheLoop)
