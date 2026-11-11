# Copyright (c) Microsoft. All rights reserved.

"""Model-free tools and workflow factories for resource-ownership tests."""

from __future__ import annotations

from typing import Any

from agent_framework import Agent, AgentExecutor, BaseChatClient, FunctionTool, Workflow, WorkflowBuilder, tool


class UnusedClient(BaseChatClient):
    async def _inner_get_response(self, **kwargs: Any) -> Any:
        raise AssertionError("Ownership validation must not call the model.")


@tool
def shared_function(value: str) -> str:
    """Return a value without accessing external services."""
    return value


@tool
async def shared_async_function(value: str) -> str:
    """Return a value asynchronously without accessing external services."""
    return value


class MutableToolOwner:
    def __init__(self) -> None:
        self.calls = 0

    @tool
    def count(self, value: str) -> str:
        """Count calls and return the input."""
        self.calls += 1
        return value


class CustomFunctionTool(FunctionTool):
    pass


def mutable_function_tool(kind: str) -> FunctionTool:
    if kind == "bound":
        return MutableToolOwner().count
    if kind == "closure":
        calls: list[str] = []

        @tool
        def capture(value: str) -> str:
            """Record and return the input."""
            calls.append(value)
            return value

        return capture
    if kind == "subclass":
        return CustomFunctionTool(name="custom", func=shared_function.func)
    if kind == "parser":
        return FunctionTool(name="parser", func=shared_function.func, result_parser=MutableToolOwner().count)
    return FunctionTool(name="limited", func=shared_function.func, **{kind: 1})


def workflow_with_tools(tools: list[Any], *, client: BaseChatClient | None = None) -> Workflow:
    agent = Agent(client=client or UnusedClient(), name="agent", tools=tools)
    return WorkflowBuilder(start_executor=AgentExecutor(agent, id="agent")).build()
