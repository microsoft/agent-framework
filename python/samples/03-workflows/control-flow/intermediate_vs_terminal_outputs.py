# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import (
    Message,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowExecutor,
    executor,
)
from typing_extensions import Never

"""
Sample: Workflow Output vs Intermediate Output labeling

What this sample shows
- How ``WorkflowBuilder(output_from=[...])`` designates which executors emit
  Workflow Output.
- How ``WorkflowBuilder(intermediate_output_from=[...])`` designates which executor
  yields surface as Intermediate Output (``type='intermediate'`` events).
- How unlisted executor yields are hidden from caller-facing output/intermediate
  events in explicit designation mode.
- How the same workflow wrapped via ``workflow.as_agent()`` translates intermediate
  events to ``text_reasoning`` content so existing ``.text`` accessors keep
  returning Workflow Output only.
- How a sub-workflow embedded via ``WorkflowExecutor`` bubbles its intermediate
  emissions up through the parent's event stream, attributed to the
  ``WorkflowExecutor`` id rather than the child's internal executor ids.

The output selection contract:
- Compatibility mode: when neither ``output_from`` nor ``intermediate_output_from``
  is provided, every ``yield_output`` produces Workflow Output and a deprecation
  warning points to explicit selection.
- Explicit selection mode: provide either ``output_from`` or
  ``intermediate_output_from``. Executors selected by ``output_from`` emit Workflow Output
  (``type='output'`` events); executors selected by ``intermediate_output_from`` emit
  Intermediate Output (``type='intermediate'`` events); unselected executor yields are
  hidden from the stream and ``WorkflowRunResult`` output accessors.
- Validation: explicit selections must not both be empty; duplicate executor entries,
  overlap between Workflow Output and Intermediate Output, unknown executors, invalid
  literals, and selected executors without workflow output types are rejected.

Prerequisites
- No external services required.
"""


@executor(id="planner")
async def planner(messages: list[Message], ctx: WorkflowContext[list[Message], str]) -> None:
    """Intermediate step: emits a visible progress note, then forwards."""
    prompt = messages[0].text if messages else ""
    await ctx.yield_output(f"plan: starting work on '{prompt}'")
    await ctx.send_message(messages)


@executor(id="researcher")
async def researcher(messages: list[Message], ctx: WorkflowContext[list[Message], str]) -> None:
    """Intermediate step: emits visible progress, then forwards."""
    prompt = messages[0].text if messages else ""
    await ctx.yield_output(f"research: gathering data for '{prompt}'")
    await ctx.send_message(messages)


@executor(id="answerer")
async def answerer(messages: list[Message], ctx: WorkflowContext[Never, str]) -> None:
    """Designated Workflow Output: emits the workflow's answer."""
    prompt = messages[0].text if messages else ""
    await ctx.yield_output(f"final answer to '{prompt}': 42")


async def main() -> None:
    # Build with explicit Workflow Output and Intermediate Output selections.
    # `answerer` produces type='output' events; planner and researcher produce
    # visible type='intermediate' events.
    workflow = (
        WorkflowBuilder(
            start_executor=planner,
            output_from=[answerer],
            intermediate_output_from=[planner, researcher],
        )
        .add_edge(planner, researcher)
        .add_edge(researcher, answerer)
        .build()
    )

    initial = [Message(role="user", contents=["life, the universe, and everything"])]

    print("=== Streaming events (workflow.run(stream=True)) ===")
    async for event in workflow.run(initial, stream=True):
        if event.type == "intermediate":
            print(f"  [intermediate] {event.executor_id}: {event.data}")
        elif event.type == "output":
            print(f"  [output]       {event.executor_id}: {event.data}")

    # WorkflowRunResult.get_outputs() filters to type='output' events, so it
    # only returns the selected Workflow Output yield.
    print("\n=== Non-streaming run().get_outputs() ===")
    result = await workflow.run(initial)
    print(f"  outputs: {result.get_outputs()}")

    # When the same workflow is wrapped via as_agent(), intermediate events
    # surface as ``text_reasoning`` content; Workflow Output surfaces as
    # ``text`` content. Existing callers reading ``response.text`` get only
    # the selected Workflow Output because ``.text`` filters to text content.
    print("\n=== workflow.as_agent() -- intermediate -> text_reasoning content ===")
    agent = workflow.as_agent("planner-agent")
    response = await agent.run("life, the universe, and everything")
    print(f"  response.text (Workflow Output only): {response.text!r}")
    reasoning = " | ".join(
        c.text for m in response.messages for c in m.contents if c.type == "text_reasoning" and c.text is not None
    )
    print(f"  reasoning content (intermediates): {reasoning!r}")

    # Embed the same workflow as a node inside a larger workflow via WorkflowExecutor.
    # Child intermediate emissions are forwarded to the parent's event stream with the
    # WorkflowExecutor's id as the source, so outer callers don't have to know the
    # child's internal executor layout. The 'intermediate' label is preserved across
    # the boundary regardless of how the parent designates the WorkflowExecutor.
    print("\n=== Embedding as a sub-workflow -- intermediates bubble up ===")
    sub = WorkflowExecutor(workflow, id="sub")

    @executor(id="parent_sink")
    async def parent_sink(message: str, ctx: WorkflowContext[Never, str]) -> None:
        await ctx.yield_output(message)

    parent_workflow = WorkflowBuilder(start_executor=sub, output_from=[parent_sink]).add_edge(sub, parent_sink).build()

    async for event in parent_workflow.run(initial, stream=True):
        if event.type == "intermediate":
            print(f"  [intermediate] {event.executor_id}: {event.data}")
        elif event.type == "output":
            print(f"  [output]       {event.executor_id}: {event.data}")

    """
    Sample output:

    === Streaming events (workflow.run(stream=True)) ===
      [intermediate] planner: plan: starting work on 'life, the universe, and everything'
      [intermediate] researcher: research: gathering data for 'life, the universe, and everything'
      [output]       answerer: final answer to 'life, the universe, and everything': 42

    === Non-streaming run().get_outputs() ===
      outputs: ["final answer to 'life, the universe, and everything': 42"]

    === workflow.as_agent() -- intermediate -> text_reasoning content ===
      response.text (Workflow Output only): "final answer to 'life, the universe, and everything': 42"
      reasoning content (intermediates): "plan: starting work on ... | research: gathering data for ..."

    === Embedding as a sub-workflow -- intermediates bubble up ===
      [intermediate] sub: plan: starting work on 'life, the universe, and everything'
      [intermediate] sub: research: gathering data for 'life, the universe, and everything'
      [output]       parent_sink: final answer to 'life, the universe, and everything': 42
    """


if __name__ == "__main__":
    asyncio.run(main())
