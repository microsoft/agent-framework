# Copyright (c) Microsoft. All rights reserved.

"""Route to mutually exclusive branches (B or C) and wire both exits to the next stage."""

import asyncio

from agent_framework import (
    Executor,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowOutputEvent,
    handler,
)


class Router(Executor):
    @handler
    async def route(self, text: str, ctx: WorkflowContext[str]) -> None:
        # Fan-out selection will choose the branch; we just forward the text.
        await ctx.send_message(text)


class BranchUpper(Executor):
    @handler
    async def upper(self, text: str, ctx: WorkflowContext[str]) -> None:
        await ctx.send_message(text.upper())


class BranchLower(Executor):
    @handler
    async def lower(self, text: str, ctx: WorkflowContext[str]) -> None:
        await ctx.send_message(text.lower())


class NextStage(Executor):
    @handler
    async def consume(self, text: str, ctx: WorkflowContext[str, str]) -> None:
        await ctx.yield_output(f"next:{text}")


def select_branch(text: str, targets: list[str]) -> list[str]:
    # Route to exactly one branch based on content
    return [targets[0]] if text.endswith("!") else [targets[1]]  # toggle destination


async def main() -> None:
    # Build the branching connection: A -> (B | C) mutually exclusive via selection_func.
    branch_conn = (
        WorkflowBuilder()
        .add_multi_selection_edge_group(
            Router(id="router"),
            [BranchUpper(id="upper"), BranchLower(id="lower")],
            selection_func=select_branch,
        )
        .set_start_executor("router")
    )

    # Downstream connection that expects str inputs
    next_conn = WorkflowBuilder().set_start_executor(NextStage(id="next"))

    builder = WorkflowBuilder()
    branch_handle = builder.add_workflow(branch_conn, prefix="branch")
    next_handle = builder.add_workflow(next_conn, prefix="down")

    # Wire both branch exits to the next connection start; only the active branch fires.
    for out_point in branch_handle.outputs:
        builder.connect(out_point, next_handle.start)

    builder.set_start_executor(branch_handle.start)

    workflow = builder.build()
    print("Outputs:")
    async for event in workflow.run_stream("RouteMe!"):
        if isinstance(event, WorkflowOutputEvent):
            print(event.data)

    """
    Sample output:

    Outputs:
    next:ROUTEME!
    """


if __name__ == "__main__":
    asyncio.run(main())
