# Workflow and orchestration builder

Use this path when explicit control flow, multiple participants, resumable progress, or caller-visible intermediate work
matters.

## Selection

| Need | API and package |
| --- | --- |
| Simple Pythonic async composition | Experimental `@workflow` from `agent-framework-core` |
| Cached calls, step events, or step-level checkpoint replay | Experimental `@step` inside `@workflow` |
| Explicit typed topology, edges, executors, routing, and outputs | `WorkflowBuilder` from `agent-framework-core` |
| Standard multi-agent collaboration pattern | Builder from released `agent-framework-orchestrations` |
| YAML-defined actions and routing | `WorkflowFactory` from `agent-framework-declarative`; read `declarative.md` |

Prefer a plain agent or harness when an inspectable execution path is not part of the requirement.

## Functional workflow

`@workflow` and `@step` are experimental. The decorator creates a stateless definition; call `build()` to create a
stateful workflow for one logical caller or session.

```python
from agent_framework import workflow


async def normalize(text: str) -> str:
    return text.strip().upper()


@workflow
async def text_workflow(text: str) -> str:
    return await normalize(text)


result = await text_workflow.build().run(" hello ")
print(result.get_outputs()[0])
```

Normal async functions work inside a functional workflow. Add `@step` only where caching, checkpoint replay, event
emission, or step-level observability justify it.

## Graph workflow

Use executors and edges when explicit routing and typed data flow matter:

```python
from agent_framework import WorkflowBuilder, WorkflowContext, executor
from typing_extensions import Never


@executor(id="normalize")
async def normalize(text: str, ctx: WorkflowContext[str]) -> None:
    await ctx.send_message(text.strip().upper())


@executor(id="finish")
async def finish(text: str, ctx: WorkflowContext[Never, str]) -> None:
    await ctx.yield_output(text)


workflow = WorkflowBuilder(start_executor=normalize).add_edge(normalize, finish).build()
result = await workflow.run(" hello ")
```

Build a fresh workflow when executors or wrapped agents hold mutable run-specific state.

## Agents in workflows

Agents can be workflow executors:

```python
workflow = WorkflowBuilder(start_executor=writer).add_edge(writer, reviewer).build()
result = await workflow.run("Draft a product announcement.")
```

Decide whether each participant needs an independent session, service-managed history, tools, middleware, or context.
Do not assume one agent's session is valid for another.

## Standard orchestrations

Install the released orchestration package when using these builders:

```bash
uv add agent-framework-orchestrations
```

Import from `agent_framework.orchestrations`:

- `SequentialBuilder`: staged output from one participant to the next.
- `ConcurrentBuilder`: fan-out to participants and aggregate.
- `HandoffBuilder`: transfer control among configured specialists.
- `GroupChatBuilder`: managed multi-participant conversation.
- `MagenticBuilder`: manager/planner-driven collaboration.

Use the standard builder before implementing an equivalent custom graph.

## Output selection

Configure `output_from` for caller-facing workflow output and `intermediate_output_from` for progress or supporting
outputs. Without explicit selection, output-capable executors use the workflow's documented default behavior.

When exposing a workflow through `workflow.as_agent()`, verify that its start executor accepts agent message input and
that callers actually require the `Agent` contract. Prefer native workflow hosting where the host supports it.

## Agent-to-workflow migration

Converting one agent into a workflow changes contracts, state, outputs, and often deployment behavior:

1. Record the current input, response, tools, middleware, context, session, and hosting contract.
2. Choose a functional workflow, graph workflow, or standard orchestration.
3. Split responsibilities only where the split changes behavior or observability.
4. Define data passed between stages.
5. Select final and intermediate outputs.
6. Preserve session and history behavior intentionally.
7. Revisit tool approval across every participant and branch.
8. Keep an agent adapter only when the external contract requires it.

## Gotchas

- Functional workflow definitions must be built before running.
- A built workflow is stateful and cannot run concurrently.
- Handoff relationships must be configured explicitly.
- Magentic participants need stable, unique names.
- Checkpoint resume requires stable workflow, executor, and participant identities.
- Human approval of a tool call and human input at a workflow transition are different mechanisms.
- Workflow streams include framework events in addition to application output.

## Validation

1. Run the smallest graph with deterministic executors before adding model calls.
2. Assert final and intermediate outputs separately.
3. Exercise every route or branch.
4. Test suspend/resume when human input or checkpoints are used.
5. Smoke-test streaming event types when callers consume streams.
6. Verify participant sessions, approval behavior, and error propagation.
7. Inspect a visualization when topology is non-trivial.

Current examples:

- [Functional workflow](https://github.com/microsoft/agent-framework/blob/main/python/samples/01-get-started/05a_functional_workflow_basics.py)
- [Graph workflow](https://github.com/microsoft/agent-framework/blob/main/python/samples/01-get-started/05c_first_graph_workflow.py)
- [Agents in a workflow](https://github.com/microsoft/agent-framework/blob/main/python/samples/03-workflows/_start-here/step2_agents_in_a_workflow.py)
