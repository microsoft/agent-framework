# Copyright (c) Microsoft. All rights reserved.

import asyncio
from dataclasses import dataclass

from typing_extensions import Never

from agent_framework import (
    Executor,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowExecutor,
    handler,
)


@dataclass
class SimpleRequest:
    """Simple request for testing."""

    text: str


@dataclass
class SimpleResponse:
    """Simple response for testing."""

    result: str


class SimpleSubExecutor(Executor):
    """Simple executor for sub-workflow."""

    def __init__(self):
        super().__init__(id="simple_sub")

    @handler
    async def process(self, request: SimpleRequest, ctx: WorkflowContext[Never, SimpleResponse]) -> None:
        """Process a simple request."""
        # Just echo back with prefix and complete
        response = SimpleResponse(result=f"processed: {request.text}")
        await ctx.yield_output(response)


class SimpleParent(Executor):
    """Simple parent executor."""

    result: SimpleResponse | None = None

    def __init__(self):
        super().__init__(id="simple_parent")

    @handler
    async def start(self, text: str, ctx: WorkflowContext[SimpleRequest]) -> None:
        """Start the process."""
        request = SimpleRequest(text=text)
        await ctx.send_message(request, target_id="sub_workflow")

    @handler
    async def collect(self, response: SimpleResponse, ctx: WorkflowContext) -> None:
        """Collect the result."""
        self.result = response


async def test_simple_sub_workflow():
    """Test the simplest possible sub-workflow."""
    # Create sub-workflow with dummy executor to satisfy validation
    sub_executor = SimpleSubExecutor()

    class DummyExecutor(Executor):
        def __init__(self):
            super().__init__(id="dummy")

        @handler
        async def process(self, message: object, ctx: WorkflowContext) -> None:
            pass  # Do nothing

    dummy = DummyExecutor()
    sub_workflow = (
        WorkflowBuilder()
        .set_start_executor(sub_executor)
        .add_edge(sub_executor, dummy)  # Add edge to satisfy validation
        .build()
    )

    # Create parent workflow
    parent = SimpleParent()
    workflow_executor = WorkflowExecutor(sub_workflow, id="sub_workflow")

    main_workflow = (
        WorkflowBuilder()
        .set_start_executor(parent)
        .add_edge(parent, workflow_executor)
        .add_edge(workflow_executor, parent)
        .build()
    )

    # Run the workflow
    await main_workflow.run("hello world")

    # Check result
    assert parent.result is not None
    assert parent.result.result == "processed: hello world"


if __name__ == "__main__":
    # Run the simple test
    asyncio.run(test_simple_sub_workflow())
