# Workflow and orchestration builder

Use a workflow when execution order, routing, parallelism, multiple participants, checkpoints, human input, or
intermediate outputs are part of the product contract.

## Choose the workflow API

| Need | API |
| --- | --- |
| Native Python control flow | Experimental `@workflow` |
| Cached or checkpoint-replayable function calls | Experimental `@step` |
| Explicit typed graph and routing | `WorkflowBuilder` |
| Standard multi-agent collaboration | `agent-framework-orchestrations` builders |
| YAML-defined actions and routing | `WorkflowFactory`; read `declarative.md` |

Read [workflow concepts](https://learn.microsoft.com/agent-framework/concepts/workflows/) and the relevant API
docstrings for signatures and execution options.

## Stable design rules

- A functional workflow definition must be built before running; each built workflow owns mutable execution state.
- Build fresh workflows when executors or wrapped agents hold run-specific state.
- Builders that accept `SupportsAgentRun` can use custom or remote agent implementations. `HandoffBuilder` accepts
  concrete `Agent` participants only.
- Use standard sequential, concurrent, handoff, group-chat, or Magentic builders before recreating those patterns.
- Select caller-facing output separately from intermediate progress.
- Wrap a workflow as an agent only when callers require the agent contract. Prefer native workflow hosting when the
  host supports it.

## Agent-to-workflow migration

Before splitting an agent into stages, record its input, response, tools, middleware, context, session, and hosting
contract. Split responsibilities only where the topology changes correctness or observability. Define the messages
between stages, final output, intermediate output, session ownership, and approval behavior explicitly.

## Gotchas

- Workflow instances are stateful and cannot run concurrently.
- Checkpoint resume requires stable workflow, executor, and participant identities.
- Sessions are not automatically interchangeable between participants.
- Tool approval and workflow human input are different suspension mechanisms.
- Workflow streams include framework events in addition to application output.

## Validation

Exercise every route with deterministic executors first. Test final and intermediate outputs separately, then test
streaming, suspension/resume, participant sessions, approvals, and error propagation where used.

## Learn more

- [Workflow concepts](https://learn.microsoft.com/agent-framework/concepts/workflows/)
- [Functional workflow sample](https://github.com/microsoft/agent-framework/blob/main/python/samples/01-get-started/05a_functional_workflow_basics.py)
- [Graph workflow sample](https://github.com/microsoft/agent-framework/blob/main/python/samples/01-get-started/05c_first_graph_workflow.py)
- [Workflow samples](https://github.com/microsoft/agent-framework/tree/main/python/samples/03-workflows)
