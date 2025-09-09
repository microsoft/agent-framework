# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework.workflow import WorkflowBuilder, WorkflowCompletedEvent, WorkflowContext, executor

"""
Sample: Foundational sequential workflow with streaming using function-style executors.

Two lightweight steps run in order. The first converts text to uppercase.
The second reverses the text and completes the workflow. Events are printed as they arrive from run_stream.

Purpose:
Show how to declare executors with the @executor decorator, connect them with WorkflowBuilder,
pass intermediate values using ctx.send_message, and signal completion with ctx.add_event by emitting a
WorkflowCompletedEvent. Demonstrate how streaming exposes ExecutorInvokeEvent and WorkflowCompletedEvent
for observability.

Prerequisites:
- No external services required.
"""


# Step 1: Define methods using the executor decorator.
@executor(id="upper_case_executor")
async def to_upper_case(text: str, ctx: WorkflowContext[str]) -> None:
    """Transform the input to uppercase and forward it to the next step.

    Concepts:
    - The @executor decorator registers this function as a workflow node.
    - WorkflowContext[str] indicates that this node emits a string payload downstream.
    """
    result = text.upper()

    # Send the intermediate result to the next executor in the workflow graph.
    await ctx.send_message(result)


@executor(id="reverse_text_executor")
async def reverse_text(text: str, ctx: WorkflowContext[str]) -> None:
    """Reverse the input and complete the workflow with the final result.

    Concepts:
    - Terminal nodes publish a WorkflowCompletedEvent using ctx.add_event.
    - No further messages are forwarded after completion.
    """
    result = text[::-1]

    # Emit the terminal event that carries the final output for this run.
    await ctx.add_event(WorkflowCompletedEvent(result))


async def main():
    """Build a two-step sequential workflow and run it with streaming to observe events."""
    # Step 2: Build the workflow with the defined edges.
    # Order matters. upper_case_executor runs first, then reverse_text_executor.
    workflow = WorkflowBuilder().add_edge(to_upper_case, reverse_text).set_start_executor(to_upper_case).build()

    # Step 3: Run the workflow and stream events in real time.
    completion_event = None
    async for event in workflow.run_stream("hello world"):
        # You will see executor invoke and completion events, and then the final WorkflowCompletedEvent.
        print(f"Event: {event}")
        if isinstance(event, WorkflowCompletedEvent):
            # The WorkflowCompletedEvent contains the final result.
            completion_event = event

    # Print the final result after the streaming loop concludes.
    if completion_event:
        print(f"Workflow completed with result: {completion_event.data}")

    """
    Sample Output:

    Event: ExecutorInvokeEvent(executor_id=upper_case_executor)
    Event: ExecutorCompletedEvent(executor_id=upper_case_executor)
    Event: ExecutorInvokeEvent(executor_id=reverse_text_executor)
    Event: WorkflowCompletedEvent(data=DLROW OLLEH)
    Event: ExecutorCompletedEvent(executor_id=reverse_text_executor)
    Workflow completed with result: DLROW OLLEH
    """


if __name__ == "__main__":
    asyncio.run(main())
