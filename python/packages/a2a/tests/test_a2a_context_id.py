# Copyright (c) Microsoft. All rights reserved.

"""Tests for A2AAgent context_id propagation from session."""

from unittest.mock import MagicMock

from agent_framework import AgentSession, Content, Message
from agent_framework.a2a import A2AAgent


class MockA2AClient:
    """Minimal mock for capturing sent messages."""

    def __init__(self) -> None:
        self.sent_messages: list = []

    async def send_message(self, message):  # type: ignore[no-untyped-def]
        self.sent_messages.append(message)
        return
        yield  # make it an async generator  # noqa: RET504


def test_context_id_derived_from_session() -> None:
    """When a session is provided, _prepare_message_for_a2a uses session.session_id as context_id."""
    agent = A2AAgent(name="test", client=MagicMock(), http_client=None)
    message = Message(role="user", contents=[Content.from_text(text="Hello")])

    session = AgentSession()
    a2a_msg = agent._prepare_message_for_a2a(message, context_id=session.session_id)

    assert a2a_msg.context_id == session.session_id


def test_context_id_falls_back_to_additional_properties() -> None:
    """When context_id kwarg is None, additional_properties['context_id'] is used."""
    agent = A2AAgent(name="test", client=MagicMock(), http_client=None)
    message = Message(
        role="user",
        contents=[Content.from_text(text="Hello")],
        additional_properties={"context_id": "from-props"},
    )

    a2a_msg = agent._prepare_message_for_a2a(message, context_id=None)

    assert a2a_msg.context_id == "from-props"


def test_context_id_generates_uuid_when_no_source() -> None:
    """When no context_id is available from session or properties, a UUID is generated."""
    agent = A2AAgent(name="test", client=MagicMock(), http_client=None)
    message = Message(role="user", contents=[Content.from_text(text="Hello")])

    a2a_msg = agent._prepare_message_for_a2a(message, context_id=None)

    # Should be a non-empty hex string (uuid4().hex)
    assert a2a_msg.context_id is not None
    assert len(a2a_msg.context_id) == 32  # uuid4().hex is 32 chars


def test_explicit_context_id_overrides_additional_properties() -> None:
    """When both context_id kwarg and additional_properties are set, kwarg wins."""
    agent = A2AAgent(name="test", client=MagicMock(), http_client=None)
    message = Message(
        role="user",
        contents=[Content.from_text(text="Hello")],
        additional_properties={"context_id": "from-props"},
    )

    a2a_msg = agent._prepare_message_for_a2a(message, context_id="from-session")

    assert a2a_msg.context_id == "from-session"


def test_context_id_not_duplicated_in_metadata() -> None:
    """context_id should be filtered from wire metadata to avoid duplication."""
    agent = A2AAgent(name="test", client=MagicMock(), http_client=None)
    message = Message(
        role="user",
        contents=[Content.from_text(text="Hello")],
        additional_properties={"context_id": "ctx-123", "trace_id": "trace-456"},
    )

    a2a_msg = agent._prepare_message_for_a2a(message, context_id="ctx-123")

    # context_id should NOT appear in metadata
    assert a2a_msg.metadata == {"trace_id": "trace-456"}
    # But should be set on the message itself
    assert a2a_msg.context_id == "ctx-123"
