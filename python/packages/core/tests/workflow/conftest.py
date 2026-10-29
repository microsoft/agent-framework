# Copyright (c) Microsoft. All rights reserved.

from collections.abc import Callable
from typing import Any

import pytest

from agent_framework import (
    Case,
    Default,
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


@pytest.fixture
def selected_reply_workflow() -> Callable[
    [str, bool], tuple[Workflow, dict[str, Workflow], dict[str, SubWorkflowRequestMessage], list[str]]
]:
    def build(
        routing: str, select_both: bool = False
    ) -> tuple[Workflow, dict[str, Workflow], dict[str, SubWorkflowRequestMessage], list[str]]:
        requests: dict[str, SubWorkflowRequestMessage] = {}
        calls: list[str] = []

        class Requester(Executor):
            @handler
            async def start(self, message: str, ctx: WorkflowContext) -> None:
                await ctx.request_info(message, bool, request_id="shared")

            @response_handler
            async def respond(self, original: str, approved: bool, ctx: WorkflowContext[Any, str]) -> None:
                await ctx.yield_output(original)

        class Coordinator(Executor):
            @handler
            async def start(self, message: str, ctx: WorkflowContext[str]) -> None:
                await ctx.send_message(message, target_id=message)

            @handler
            async def reply(
                self, messages: list[SubWorkflowResponseMessage], ctx: WorkflowContext[SubWorkflowResponseMessage]
            ) -> None:
                for message in messages:
                    await ctx.send_message(message)

            @handler
            async def intercept(self, request: SubWorkflowRequestMessage, ctx: WorkflowContext) -> None:
                requests[request.executor_id] = request

        def select(message: Any, targets: list[str]) -> list[str]:
            if isinstance(message, SubWorkflowResponseMessage):
                calls.append("selection")
                return targets if select_both else ["first"]
            return targets

        async def first_condition(message: Any) -> bool:
            if isinstance(message, SubWorkflowResponseMessage):
                calls.append("first")
            return True

        async def second_condition(message: Any) -> bool:
            if isinstance(message, SubWorkflowResponseMessage):
                calls.append("second")
                return select_both
            return True

        def first_case(message: Any) -> bool:
            if isinstance(message, SubWorkflowResponseMessage):
                calls.append("switch")
                return True
            return message == "first"

        children = {
            name: WorkflowBuilder(start_executor=Requester(id="requester")).build() for name in ("first", "second")
        }
        wrappers = {
            name: WorkflowExecutor(child, id=name, allow_direct_output=True) for name, child in children.items()
        }
        coordinator = Coordinator(id="coordinator")
        builder = WorkflowBuilder(start_executor=coordinator)
        if routing == "condition":
            builder.add_edge(coordinator, wrappers["first"], condition=first_condition)
            builder.add_edge(coordinator, wrappers["second"], condition=second_condition)
        elif routing == "selection":
            builder.add_multi_selection_edge_group(coordinator, list(wrappers.values()), select)
        else:
            builder.add_switch_case_edge_group(
                coordinator, [Case(condition=first_case, target=wrappers["first"]), Default(target=wrappers["second"])]
            )
        for wrapper in wrappers.values():
            builder.add_edge(wrapper, coordinator)
        return builder.build(), children, requests, calls

    return build
