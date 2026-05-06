# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import (
    Message,
    WorkflowBuilder,
    WorkflowContext,
    executor,
)
from typing_extensions import Never

"""
Sample: Intermediate vs terminal output labeling

What this sample shows
- How ``WorkflowBuilder(output_executors=[...])`` designates which executors emit
  the workflow's terminal output.
- How yields from non-designated executors automatically surface as
  ``type='intermediate'`` events, while yields from designated executors surface
  as ``type='output'``.
- How the same workflow wrapped via ``workflow.as_agent()`` translates intermediate
  events to ``text_reasoning`` content so existing ``.text`` accessors keep
  returning terminal-only output.

The contract on ``output_executors``:
- ``None`` (default, legacy): every ``yield_output`` produces ``type='output'``.
  Emits a ``DeprecationWarning`` at build() time recommending explicit designation.
- ``[]`` (explicit empty list): strict mode, no terminals. Every yield is
  ``type='intermediate'``; ``WorkflowRunResult.get_outputs()`` returns ``[]``.
- ``[X, ...]`` (explicit list): strict mode. Yields from designated executors
  produce ``type='output'``; all other yields produce ``type='intermediate'``.

Prerequisites
- No external services required.
"""


@executor(id="planner")
async def planner(messages: list[Message], ctx: WorkflowContext[list[Message], str]) -> None:
    """Non-designated step: emits an intermediate progress note, then forwards."""
    prompt = messages[0].text if messages else ""
    await ctx.yield_output(f"plan: starting work on '{prompt}'")
    await ctx.send_message(messages)


@executor(id="researcher")
async def researcher(messages: list[Message], ctx: WorkflowContext[list[Message], str]) -> None:
    """Non-designated step: emits intermediate progress, then forwards."""
    prompt = messages[0].text if messages else ""
    await ctx.yield_output(f"research: gathering data for '{prompt}'")
    await ctx.send_message(messages)


@executor(id="answerer")
async def answerer(messages: list[Message], ctx: WorkflowContext[Never, str]) -> None:
    """Designated terminal: emits the workflow's final answer."""
    prompt = messages[0].text if messages else ""
    await ctx.yield_output(f"final answer to '{prompt}': 42")


async def main() -> None:
    # Build with explicit output_executors=[answerer]. Only `answerer` yields
    # produce type='output' events; planner and researcher emit type='intermediate'.
    workflow = (
        WorkflowBuilder(start_executor=planner, output_executors=[answerer])
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
    # only returns the designated terminal yield.
    print("\n=== Non-streaming run().get_outputs() ===")
    result = await workflow.run(initial)
    print(f"  outputs: {result.get_outputs()}")

    # When the same workflow is wrapped via as_agent(), intermediate events
    # surface as ``text_reasoning`` content; the terminal event surfaces as
    # ``text`` content. Existing callers reading ``response.text`` get only
    # the terminal answer because ``.text`` filters to text content.
    print("\n=== workflow.as_agent() — intermediate → text_reasoning content ===")
    agent = workflow.as_agent("planner-agent")
    response = await agent.run("life, the universe, and everything")
    print(f"  response.text (terminal only): {response.text!r}")
    reasoning = " | ".join(
        c.text for m in response.messages for c in m.contents if c.type == "text_reasoning"
    )
    print(f"  reasoning content (intermediates): {reasoning!r}")

    """
    Sample output:

    === Streaming events (workflow.run(stream=True)) ===
      [intermediate] planner: plan: starting work on 'life, the universe, and everything'
      [intermediate] researcher: research: gathering data for 'life, the universe, and everything'
      [output]       answerer: final answer to 'life, the universe, and everything': 42

    === Non-streaming run().get_outputs() ===
      outputs: ["final answer to 'life, the universe, and everything': 42"]

    === workflow.as_agent() — intermediate → text_reasoning content ===
      response.text (terminal only): "final answer to 'life, the universe, and everything': 42"
      reasoning content (intermediates): "plan: starting work on ... | research: gathering data for ..."
    """


if __name__ == "__main__":
    asyncio.run(main())
