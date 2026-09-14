# Copyright (c) Microsoft. All rights reserved.

"""Factory resolution leaves execution-object ownership to the application."""

from typing import Any

import pytest
from agent_framework import AgentExecutor, AgentResponse, AgentSession, Message, WorkflowAgent, WorkflowBuilder

from agent_framework_foundry_hosting._agent_factory import AgentFactoryResolver


class _SlottedAgent:
    __slots__ = ("description", "id", "name")

    def __init__(self) -> None:
        self.id = "slotted"
        self.name: str | None = "slotted"
        self.description: str | None = None

    def create_session(self, *, session_id: str | None = None) -> AgentSession:
        return AgentSession(session_id=session_id)

    def get_session(self, service_session_id: Any, *, session_id: str | None = None) -> AgentSession:
        return AgentSession(session_id=session_id, service_session_id=service_session_id)

    def run(self, messages: Any = None, *, stream: bool = False, session: Any = None, **kwargs: Any) -> Any:
        async def response() -> AgentResponse:
            return AgentResponse(messages=[Message("assistant", ["slotted"])])

        return response()


@pytest.mark.parametrize("asynchronous", [False, True])
async def test_factory_does_not_require_weak_reference_support(asynchronous: bool) -> None:
    calls = 0

    def factory() -> WorkflowAgent:
        nonlocal calls
        calls += 1
        executor = AgentExecutor(_SlottedAgent(), id="inner")
        return WorkflowBuilder(name="slotted-workflow", start_executor=executor).build().as_agent()

    async def async_factory() -> WorkflowAgent:
        return factory()

    resolver = AgentFactoryResolver(async_factory if asynchronous else factory)
    first = await resolver.resolve()
    second = await resolver.resolve()
    assert isinstance(first, WorkflowAgent)
    assert isinstance(second, WorkflowAgent)
    assert first is not second
    assert first.workflow.executors["inner"] is not second.workflow.executors["inner"]
    assert (await first.run("first")).text == "slotted"
    assert (await second.run("second")).text == "slotted"
    assert calls == 2


@pytest.mark.parametrize("same_wrapper", [False, True])
async def test_resolver_returns_factory_result_without_enforcing_object_ownership(same_wrapper: bool) -> None:
    executor = AgentExecutor(_SlottedAgent(), id="inner")
    agent = WorkflowBuilder(name="application-owned", start_executor=executor).build().as_agent()
    calls = 0

    def factory() -> WorkflowAgent:
        nonlocal calls
        calls += 1
        if same_wrapper:
            return agent
        return WorkflowBuilder(name="application-owned", start_executor=executor).build().as_agent()

    resolver = AgentFactoryResolver(factory)
    first = await resolver.resolve()
    second = await resolver.resolve()
    assert isinstance(first, WorkflowAgent)
    assert isinstance(second, WorkflowAgent)
    assert first.workflow.executors["inner"] is executor
    assert second.workflow.executors["inner"] is executor
    assert (first is second) is same_wrapper
    assert calls == 2
