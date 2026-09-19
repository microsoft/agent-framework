# Copyright (c) Microsoft. All rights reserved.

"""Tests for service-managed thread IDs, and service-generated response ids."""

from typing import Any

from ag_ui.core import RunFinishedEvent, RunStartedEvent
from agent_framework import Content
from agent_framework._types import AgentResponse, AgentResponseUpdate, ChatResponseUpdate, ResponseStream


async def test_service_thread_id_when_there_are_updates(stub_agent):
    """Test that service-managed thread IDs (conversation_id) are correctly set as the thread_id in events."""
    from agent_framework.ag_ui import AgentFrameworkAgent

    updates: list[AgentResponseUpdate] = [
        AgentResponseUpdate(
            contents=[Content.from_text(text="Hello, user!")],
            response_id="resp_67890",
            raw_representation=ChatResponseUpdate(
                contents=[Content.from_text(text="Hello, user!")],
                conversation_id="conv_12345",
                response_id="resp_67890",
            ),
        )
    ]
    agent = stub_agent(updates=updates)
    wrapper = AgentFrameworkAgent(agent=agent)

    input_data = {
        "messages": [{"role": "user", "content": "Hi"}],
    }

    events: list[Any] = []
    async for event in wrapper.run(input_data):
        events.append(event)

    assert isinstance(events[0], RunStartedEvent)
    assert events[0].run_id == "resp_67890"
    assert events[0].thread_id == "conv_12345"
    assert isinstance(events[-1], RunFinishedEvent)


async def test_service_thread_id_when_no_user_message(stub_agent):
    """Test when user submits no messages, emitted events still have with a thread_id"""
    from agent_framework.ag_ui import AgentFrameworkAgent

    updates: list[AgentResponseUpdate] = []
    agent = stub_agent(updates=updates)
    wrapper = AgentFrameworkAgent(agent=agent)

    input_data: dict[str, list[dict[str, str]]] = {
        "messages": [],
    }

    events: list[Any] = []
    async for event in wrapper.run(input_data):
        events.append(event)

    assert len(events) == 2
    assert isinstance(events[0], RunStartedEvent)
    assert events[0].thread_id
    assert isinstance(events[-1], RunFinishedEvent)


async def test_service_thread_id_when_user_supplied_thread_id(stub_agent):
    """Test that user-supplied thread IDs are preserved in emitted events."""
    from agent_framework.ag_ui import AgentFrameworkAgent

    updates: list[AgentResponseUpdate] = []
    agent = stub_agent(updates=updates)
    wrapper = AgentFrameworkAgent(agent=agent)

    input_data: dict[str, Any] = {"messages": [{"role": "user", "content": "Hi"}], "threadId": "conv_12345"}

    events: list[Any] = []
    async for event in wrapper.run(input_data):
        events.append(event)

    assert isinstance(events[0], RunStartedEvent)
    assert events[0].thread_id == "conv_12345"
    assert isinstance(events[-1], RunFinishedEvent)


async def test_run_started_is_emitted_before_the_first_update_when_ids_are_supplied(stub_agent):
    """With both IDs supplied, RunStarted does not wait for the agent's first update."""
    import asyncio

    from agent_framework.ag_ui import AgentFrameworkAgent

    gate = asyncio.Event()

    class SlowStartAgent(stub_agent):  # type: ignore[misc, valid-type]
        """Stands in for context providers and a first model call that take a while."""

        def run(self, messages: Any = None, *, stream: bool = False, **kwargs: Any) -> Any:
            if not stream:
                return super().run(messages, stream=stream, **kwargs)

            async def _stream() -> Any:
                await gate.wait()
                for update in self.updates:
                    yield update

            return ResponseStream(_stream(), finalizer=AgentResponse.from_updates)

    wrapper = AgentFrameworkAgent(agent=SlowStartAgent())
    input_data = {"messages": [{"role": "user", "content": "Hi"}], "threadId": "thread_1", "runId": "run_1"}

    events = wrapper.run(input_data)
    first = await asyncio.wait_for(anext(events), timeout=5)

    assert isinstance(first, RunStartedEvent)
    assert (first.thread_id, first.run_id) == ("thread_1", "run_1")

    gate.set()
    rest = [event async for event in events]
    assert not any(isinstance(event, RunStartedEvent) for event in rest)
    assert isinstance(rest[-1], RunFinishedEvent)


async def test_run_started_waits_for_the_service_run_id_when_none_is_supplied(stub_agent):
    """Without a supplied run ID, RunStarted still carries the service response ID."""
    from agent_framework.ag_ui import AgentFrameworkAgent

    updates = [AgentResponseUpdate(contents=[Content.from_text(text="Hello")], response_id="resp_1")]
    wrapper = AgentFrameworkAgent(agent=stub_agent(updates=updates))
    input_data = {"messages": [{"role": "user", "content": "Hi"}], "threadId": "thread_1"}

    events = [event async for event in wrapper.run(input_data)]

    assert isinstance(events[0], RunStartedEvent)
    assert (events[0].thread_id, events[0].run_id) == ("thread_1", "resp_1")
