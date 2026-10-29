# Copyright (c) Microsoft. All rights reserved.

"""Pytest configuration for declarative tests."""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any

import pytest
from agent_framework import (
    CheckpointStorage,
    Executor,
    SubWorkflowRequestMessage,
    SubWorkflowResponseMessage,
    Workflow,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowExecutor,
    handler,
    response_handler,
)

# Skip all tests in this directory on Python 3.14+ because powerfx doesn't support it yet
if sys.version_info >= (3, 14):
    collect_ignore_glob = ["test_*.py"]


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip all declarative tests on Python 3.14+ due to powerfx incompatibility."""
    if sys.version_info >= (3, 14):
        skip_marker = pytest.mark.skip(reason="powerfx does not support Python 3.14+")
        for item in items:
            if "declarative" in str(item.fspath):
                item.add_marker(skip_marker)


@pytest.fixture
def coordinator_relay_workflow() -> Callable[[Workflow, CheckpointStorage], Workflow]:
    """Build a parent that relays child requests without changing their IDs."""

    class Requester(Executor):
        @handler
        async def start(self, message: str, ctx: WorkflowContext) -> None:
            await ctx.request_info(message, str)

        @response_handler
        async def respond(self, original: str, response: str, ctx: WorkflowContext[Any, dict[str, str]]) -> None:
            await ctx.yield_output({"response": response})

    class Coordinator(Executor):
        @handler
        async def start(self, message: int, ctx: WorkflowContext[Any]) -> None:
            await ctx.send_message({}, target_id="mcp")
            await ctx.send_message(str(message), target_id="requester")

        @handler
        async def relay(self, request: SubWorkflowRequestMessage, ctx: WorkflowContext) -> None:
            await ctx.request_info(request, str, request_id=request.source_event.request_id)

        @response_handler
        async def respond(
            self,
            original: SubWorkflowRequestMessage,
            response: str,
            ctx: WorkflowContext[SubWorkflowResponseMessage],
        ) -> None:
            await ctx.send_message(original.create_response(response), target_id="requester")

        @handler
        async def collect(self, message: dict[str, str], ctx: WorkflowContext[dict[str, Any]]) -> None:
            await ctx.send_message({}, target_id="mcp")

    def build(mcp_workflow: Workflow, storage: CheckpointStorage) -> Workflow:
        coordinator = Coordinator(id="coordinator")
        requester = WorkflowExecutor(WorkflowBuilder(start_executor=Requester(id="pause")).build(), id="requester")
        mcp = WorkflowExecutor(mcp_workflow, id="mcp")
        return (
            WorkflowBuilder(start_executor=coordinator, checkpoint_storage=storage)
            .add_edge(coordinator, requester)
            .add_edge(requester, coordinator)
            .add_edge(coordinator, mcp)
            .build()
        )

    return build
