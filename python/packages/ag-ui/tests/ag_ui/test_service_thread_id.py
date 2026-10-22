# Copyright (c) Microsoft. All rights reserved.

"""Tests for service-managed thread IDs, and service-generated response ids."""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest
from ag_ui.core import CustomEvent, RunFinishedEvent, RunStartedEvent, StateSnapshotEvent
from agent_framework import AgentResponse, Content
from agent_framework._types import AgentResponseUpdate, ChatResponseUpdate, ResponseStream


def _gate_agent_stream(agent: Any, monkeypatch: pytest.MonkeyPatch) -> asyncio.Event:
    """Hold the agent's streamed updates until the returned event is set."""
    release = asyncio.Event()
    original_run = agent.run

    def gated_run(messages: Any = None, *, stream: bool = False, **kwargs: Any) -> Any:
        inner = original_run(messages, stream=stream, **kwargs)
        if not stream:
            return inner

        async def _gated() -> AsyncIterator[AgentResponseUpdate]:
            await release.wait()
            async for update in inner:
                yield update

        return ResponseStream(_gated(), finalizer=AgentResponse.from_updates)

    monkeypatch.setattr(agent, "run", gated_run)
    return release


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


async def test_run_started_is_emitted_before_agent_updates_when_ids_are_supplied(stub_agent, monkeypatch):
    """Supplied thread and run IDs let the run start before the agent produces its first update."""
    from agent_framework.ag_ui import AgentFrameworkAgent

    agent = stub_agent()
    release = _gate_agent_stream(agent, monkeypatch)
    wrapper = AgentFrameworkAgent(
        agent=agent,
        state_schema={"document": {"type": "string"}},
        predict_state_config={"document": {"tool": "write_doc", "tool_argument": "content"}},
    )

    input_data: dict[str, Any] = {
        "messages": [{"role": "user", "content": "Hi"}],
        "state": {"document": "draft"},
        "threadId": "thread-1",
        "runId": "run-1",
    }

    events = wrapper.run(input_data)
    opening_events = [await asyncio.wait_for(anext(events), timeout=5) for _ in range(3)]
    release.set()
    remaining_events = [event async for event in events]

    run_started, predict_state, state_snapshot = opening_events
    assert isinstance(run_started, RunStartedEvent)
    assert (run_started.thread_id, run_started.run_id) == ("thread-1", "run-1")
    assert isinstance(predict_state, CustomEvent)
    assert predict_state.name == "PredictState"
    assert isinstance(state_snapshot, StateSnapshotEvent)
    assert state_snapshot.snapshot == {"document": "draft"}
    assert not any(isinstance(event, RunStartedEvent) for event in remaining_events)
    assert any(event.type == "TEXT_MESSAGE_CONTENT" for event in remaining_events)
    assert isinstance(remaining_events[-1], RunFinishedEvent)
    assert (remaining_events[-1].thread_id, remaining_events[-1].run_id) == ("thread-1", "run-1")


async def test_run_started_waits_for_service_run_id_when_only_thread_id_is_supplied(stub_agent):
    """A missing run ID is still taken from the first update before the run starts."""
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
    wrapper = AgentFrameworkAgent(agent=stub_agent(updates=updates))

    input_data: dict[str, Any] = {"messages": [{"role": "user", "content": "Hi"}], "threadId": "thread-1"}

    events: list[Any] = [event async for event in wrapper.run(input_data)]

    run_started_events = [event for event in events if isinstance(event, RunStartedEvent)]
    assert run_started_events == [events[0]]
    assert (events[0].thread_id, events[0].run_id) == ("thread-1", "resp_67890")
    assert isinstance(events[-1], RunFinishedEvent)
