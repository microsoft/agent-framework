# Copyright (c) Microsoft. All rights reserved.

"""Tests for A2AAgent session/context_id propagation (issue #4663)."""

from __future__ import annotations

from unittest.mock import MagicMock

from a2a.types import Role as A2ARole
from agent_framework import AgentSession, Content, Message

from agent_framework_a2a._agent import A2AAgent


def _make_text_message(text: str = "hello") -> Message:
    """Create a minimal text Message for testing."""
    return Message(
        role="user",
        contents=[Content.from_text(text=text)],
    )


def _make_agent() -> A2AAgent:
    """Create an A2AAgent with a mock client for unit testing."""
    agent = A2AAgent(url="http://localhost:9999")
    agent.client = MagicMock()  # replace real client with mock
    return agent


class TestContextIdPropagation:
    """Tests verifying that session.session_id is propagated as A2A context_id."""

    def test_context_id_set_from_session(self) -> None:
        """When a session is provided, its session_id should become the A2A context_id."""
        agent = _make_agent()
        session = AgentSession(session_id="my-session-123")
        message = _make_text_message()

        a2a_msg = agent._prepare_message_for_a2a(message, context_id=session.session_id)

        assert a2a_msg.context_id == "my-session-123"

    def test_context_id_auto_generated_when_no_session(self) -> None:
        """When no context_id is provided, a random one is generated."""
        agent = _make_agent()
        message = _make_text_message()

        a2a_msg = agent._prepare_message_for_a2a(message)

        # Should have a non-empty context_id
        assert a2a_msg.context_id is not None
        assert len(a2a_msg.context_id) > 0

    def test_context_id_none_generates_random(self) -> None:
        """Explicitly passing context_id=None should also auto-generate."""
        agent = _make_agent()
        message = _make_text_message()

        a2a_msg = agent._prepare_message_for_a2a(message, context_id=None)

        assert a2a_msg.context_id is not None
        assert len(a2a_msg.context_id) > 0

    def test_different_sessions_produce_different_context_ids(self) -> None:
        """Different session IDs should produce different context_ids."""
        agent = _make_agent()
        message = _make_text_message()

        msg1 = agent._prepare_message_for_a2a(message, context_id="session-A")
        msg2 = agent._prepare_message_for_a2a(message, context_id="session-B")

        assert msg1.context_id != msg2.context_id
        assert msg1.context_id == "session-A"
        assert msg2.context_id == "session-B"

    def test_message_role_is_user(self) -> None:
        """Outgoing messages should always have role='user'."""
        agent = _make_agent()
        message = _make_text_message()

        a2a_msg = agent._prepare_message_for_a2a(message, context_id="test")

        assert a2a_msg.role == A2ARole.user

    def test_message_parts_preserved(self) -> None:
        """Text content should be converted to A2A TextPart."""
        agent = _make_agent()
        message = _make_text_message("test content")

        a2a_msg = agent._prepare_message_for_a2a(message, context_id="test")

        assert len(a2a_msg.parts) == 1
        assert a2a_msg.parts[0].root.text == "test content"
