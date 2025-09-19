# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import (
    Executor,
    WorkflowBuilder,
    WorkflowCompletedEvent,
    WorkflowContext,
    executor,
    handler,
)

"""
Step 1: Foundational patterns: Executors and edges

What this example shows
- Two ways to define a unit of work (an Executor node):
    1) Custom class that subclasses Executor with an async method marked by @handler.
         Signature: (text: str, ctx: WorkflowContext[str]) -> None. The typed ctx
         advertises the type this node emits via ctx.send_message(...).
    2) Standalone async function decorated with @executor using the same signature.
         Simple steps can use this form; a terminal step can emit a
         WorkflowCompletedEvent to end the workflow.

- Fluent WorkflowBuilder API:
    add_edge(A, B) to connect nodes, set_start_executor(A), then build() -> Workflow.

- Running and results:
    workflow.run(initial_input) executes the graph. The last node emits a
    WorkflowCompletedEvent that carries the final result.

Prerequisites
- No external services required.
"""


# Example 1: A custom Executor subclass
# ------------------------------------
#
# Subclassing Executor lets you define a named node with lifecycle hooks if needed.
# The work itself is implemented in an async method decorated with @handler.
#
# Handler signature contract:
# - First parameter is the typed input to this node (here: text: str)
# - Second parameter is a WorkflowContext[T], where T is the type of data this
#   node will emit via ctx.send_message (here: T is str)
#
# Within a handler you typically:
# - Compute a result
# - Forward that result to downstream node(s) using ctx.send_message(result)
class UpperCase(Executor):
    def __init__(self, id: str):
        super().__init__(id=id)

    @handler
    async def to_upper_case(self, text: str, ctx: WorkflowContext[str]) -> None:
        """Convert the input to uppercase and forward it to the next node.

        Note: The WorkflowContext is parameterized with the type this handler will
        emit. Here WorkflowContext[str] means downstream nodes should expect str.
        """
        result = text.upper()

        # Send the result to the next executor in the workflow.
        await ctx.send_message(result)


# Example 2: A standalone function-based executor
# -----------------------------------------------
#
# For simple steps you can skip subclassing and define an async function with the
# same signature pattern (typed input + WorkflowContext[T]) and decorate it with
# @executor. This creates a fully functional node that can be wired into a flow.


@executor(id="reverse_text_executor")
async def reverse_text(text: str, ctx: WorkflowContext[str]) -> None:
    """Reverse the input string and signal workflow completion.

    This node emits a terminal event using ctx.add_event(WorkflowCompletedEvent).
    The data carried by the WorkflowCompletedEvent becomes the final result of
    the workflow (returned by workflow.run(...)).
    """
    result = text[::-1]

    # Send the result with a workflow completion event.
    await ctx.add_event(WorkflowCompletedEvent(result))


async def main():
    """Build and run a simple 2-step workflow using the fluent builder API."""

    upper_case = UpperCase(id="upper_case_executor")

    # Build the workflow using a fluent pattern:
    # 1) add_edge(from_node, to_node) defines a directed edge upper_case -> reverse_text
    # 2) set_start_executor(node) declares the entry point
    # 3) build() finalizes and returns an immutable Workflow object
    workflow = WorkflowBuilder().add_edge(upper_case, reverse_text).set_start_executor(upper_case).build()

    # Run the workflow by sending the initial message to the start node.
    # The run(...) call returns an event collection; its get_completed_event()
    # provides the WorkflowCompletedEvent emitted by the terminal node.
    events = await workflow.run("hello world")
    print(events.get_completed_event())
    # Summarize the final run state (e.g., COMPLETED)
    print("Final state:", events.get_final_state())

    """
    Sample Output:

    WorkflowCompletedEvent(data=DLROW OLLEH)
    Final state: WorkflowRunState.COMPLETED
    """


if __name__ == "__main__":
    asyncio.run(main())
