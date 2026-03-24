# Copyright (c) Microsoft. All rights reserved.

"""Golden event-stream tests for the basic agentic chat scenario."""

from __future__ import annotations

from typing import Any

from agent_framework import AgentResponseUpdate, Content
from conftest import StubAgent
from event_stream import EventStream

from agent_framework_ag_ui import AgentFrameworkAgent


def _build_agent(updates: list[AgentResponseUpdate], **kwargs: Any) -> AgentFrameworkAgent:
    stub = StubAgent(updates=updates)
    return AgentFrameworkAgent(agent=stub, **kwargs)


async def _run(agent: AgentFrameworkAgent, payload: dict[str, Any]) -> EventStream:
    return EventStream([event async for event in agent.run(payload)])


BASIC_PAYLOAD: dict[str, Any] = {
    "thread_id": "thread-chat",
    "run_id": "run-chat",
    "messages": [{"role": "user", "content": "Hello"}],
}


def _text_update(text: str) -> AgentResponseUpdate:
    return AgentResponseUpdate(contents=[Content.from_text(text=text)], role="assistant")


def _snapshot_role(msg: Any) -> str:
    """Extract role string from a snapshot message (Pydantic model or dict)."""
    role = getattr(msg, "role", None) or (msg.get("role") if isinstance(msg, dict) else None)
    if role is None:
        return ""
    return str(getattr(role, "value", role))


def _snapshot_content(msg: Any) -> str:
    """Extract content string from a snapshot message."""
    content = getattr(msg, "content", None) or (msg.get("content") if isinstance(msg, dict) else "")
    return str(content) if content else ""


# ── Golden stream tests ──


async def test_basic_chat_golden_event_sequence() -> None:
    """Assert the exact event type sequence for a single text response."""
    agent = _build_agent([_text_update("Hi there!")])
    stream = await _run(agent, BASIC_PAYLOAD)

    stream.assert_strict_types(
        [
            "RUN_STARTED",
            "TEXT_MESSAGE_START",
            "TEXT_MESSAGE_CONTENT",
            "TEXT_MESSAGE_END",
            "MESSAGES_SNAPSHOT",
            "RUN_FINISHED",
        ]
    )


async def test_basic_chat_bookends() -> None:
    """RUN_STARTED is first, RUN_FINISHED is last."""
    agent = _build_agent([_text_update("reply")])
    stream = await _run(agent, BASIC_PAYLOAD)
    stream.assert_bookends()


async def test_basic_chat_text_messages_balanced() -> None:
    """Every TEXT_MESSAGE_START has a matching TEXT_MESSAGE_END."""
    agent = _build_agent([_text_update("reply")])
    stream = await _run(agent, BASIC_PAYLOAD)
    stream.assert_text_messages_balanced()


async def test_basic_chat_no_errors() -> None:
    """No RUN_ERROR events in a normal flow."""
    agent = _build_agent([_text_update("reply")])
    stream = await _run(agent, BASIC_PAYLOAD)
    stream.assert_no_run_error()


async def test_basic_chat_message_id_consistency() -> None:
    """All text events reference the same message_id."""
    agent = _build_agent([_text_update("reply")])
    stream = await _run(agent, BASIC_PAYLOAD)

    start = stream.first("TEXT_MESSAGE_START")
    content = stream.first("TEXT_MESSAGE_CONTENT")
    end = stream.first("TEXT_MESSAGE_END")
    assert start.message_id == content.message_id == end.message_id


async def test_multi_chunk_text_golden_sequence() -> None:
    """Streaming multiple chunks produces START + multiple CONTENT + END."""
    agent = _build_agent([_text_update("Hello "), _text_update("world!")])
    stream = await _run(agent, BASIC_PAYLOAD)

    stream.assert_strict_types(
        [
            "RUN_STARTED",
            "TEXT_MESSAGE_START",
            "TEXT_MESSAGE_CONTENT",
            "TEXT_MESSAGE_CONTENT",
            "TEXT_MESSAGE_END",
            "MESSAGES_SNAPSHOT",
            "RUN_FINISHED",
        ]
    )
    stream.assert_text_messages_balanced()
    stream.assert_message_ids_consistent()


async def test_messages_snapshot_contains_assistant_reply() -> None:
    """MessagesSnapshotEvent includes the assistant's accumulated text."""
    agent = _build_agent([_text_update("Hello there")])
    stream = await _run(agent, BASIC_PAYLOAD)

    snapshot = stream.messages_snapshot()
    assistant_msgs = [m for m in snapshot if _snapshot_role(m) == "assistant"]
    assert assistant_msgs, "No assistant message in snapshot"
    assert any("Hello there" in _snapshot_content(m) for m in assistant_msgs)


async def test_empty_messages_produces_start_and_finish() -> None:
    """Empty message list still produces RUN_STARTED and RUN_FINISHED."""
    agent = _build_agent([_text_update("reply")])
    payload = {"thread_id": "t1", "run_id": "r1", "messages": []}
    stream = await _run(agent, payload)

    stream.assert_bookends()
    assert "TEXT_MESSAGE_START" not in stream.types()
