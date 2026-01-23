# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for AgentEntity.

Run with: pytest tests/test_entities.py -v
"""

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any, TypeVar
from unittest.mock import AsyncMock, Mock

import pytest
from agent_framework import AgentResponse, AgentResponseUpdate, ChatMessage, Content, Role
from pydantic import BaseModel

from agent_framework_durabletask import (
    AgentEntity,
    AgentEntityStateProviderMixin,
    DurableAgentState,
    DurableAgentStateData,
    DurableAgentStateMessage,
    DurableAgentStateRequest,
    DurableAgentStateTextContent,
    RunRequest,
)
from agent_framework_durabletask._entities import DurableTaskEntityStateProvider

TState = TypeVar("TState")


class MockEntityContext:
    """Minimal durabletask EntityContext shim for tests."""

    def __init__(self, initial_state: Any = None) -> None:
        self._state = initial_state

    def get_state(
        self,
        intended_type: type[TState] | None = None,
        default: TState | None = None,
    ) -> Any:
        del intended_type
        if self._state is None:
            return default
        return self._state

    def set_state(self, new_state: Any) -> None:
        self._state = new_state


class _InMemoryStateProvider(AgentEntityStateProviderMixin):
    """Test-only state provider for AgentEntity."""

    def __init__(self, *, thread_id: str, initial_state: dict[str, Any] | None = None) -> None:
        self._thread_id = thread_id
        self._state_dict: dict[str, Any] = initial_state or {}

    def _get_state_dict(self) -> dict[str, Any]:
        return self._state_dict

    def _set_state_dict(self, state: dict[str, Any]) -> None:
        self._state_dict = state

    def _get_thread_id_from_entity(self) -> str:
        return self._thread_id


def _make_entity(agent: Any, callback: Any = None, *, thread_id: str = "test-thread") -> AgentEntity:
    return AgentEntity(agent, callback=callback, state_provider=_InMemoryStateProvider(thread_id=thread_id))


def _role_value(chat_message: DurableAgentStateMessage) -> str:
    """Helper to extract the string role from a ChatMessage."""
    role = getattr(chat_message, "role", None)
    role_value = getattr(role, "value", role)
    if role_value is None:
        return ""
    return str(role_value)


def _agent_response(text: str | None) -> AgentResponse:
    """Create an AgentResponse with a single assistant message."""
    message = (
        ChatMessage(role="assistant", text=text) if text is not None else ChatMessage(role="assistant", contents=[])
    )
    return AgentResponse(messages=[message])


class RecordingCallback:
    """Callback implementation capturing streaming and final responses for assertions."""

    def __init__(self):
        self.stream_mock = AsyncMock()
        self.response_mock = AsyncMock()

    async def on_streaming_response_update(
        self,
        update: AgentResponseUpdate,
        context: Any,
    ) -> None:
        await self.stream_mock(update, context)

    async def on_agent_response(self, response: AgentResponse, context: Any) -> None:
        await self.response_mock(response, context)


class EntityStructuredResponse(BaseModel):
    answer: float


class TestAgentEntityInit:
    """Test suite for AgentEntity initialization."""

    def test_init_creates_entity(self) -> None:
        """Test that AgentEntity initializes correctly."""
        mock_agent = Mock()

        entity = _make_entity(mock_agent)

        assert entity.agent == mock_agent
        assert len(entity.state.data.conversation_history) == 0
        assert entity.state.data.extension_data is None
        assert entity.state.schema_version == DurableAgentState.SCHEMA_VERSION

    def test_init_stores_agent_reference(self) -> None:
        """Test that the agent reference is stored correctly."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"

        entity = _make_entity(mock_agent)

        assert entity.agent.name == "TestAgent"

    def test_init_with_different_agent_types(self) -> None:
        """Test initialization with different agent types."""
        agent1 = Mock()
        agent1.__class__.__name__ = "AzureOpenAIAgent"

        agent2 = Mock()
        agent2.__class__.__name__ = "CustomAgent"

        entity1 = _make_entity(agent1)
        entity2 = _make_entity(agent2)

        assert entity1.agent.__class__.__name__ == "AzureOpenAIAgent"
        assert entity2.agent.__class__.__name__ == "CustomAgent"


class TestDurableTaskEntityStateProvider:
    """Tests for DurableTaskEntityStateProvider wrapper behavior and persistence wiring."""

    def _make_durabletask_entity_provider(
        self,
        agent: Any,
        *,
        initial_state: dict[str, Any] | None = None,
    ) -> tuple[DurableTaskEntityStateProvider, MockEntityContext]:
        """Create a DurableTaskEntityStateProvider wired to an in-memory durabletask context."""
        entity = DurableTaskEntityStateProvider()
        ctx = MockEntityContext(initial_state)
        # DurableEntity provides this hook; required for get_state/set_state to work in unit tests.
        entity._initialize_entity_context(ctx)  # type: ignore[attr-defined]
        return entity, ctx

    def test_reset_persists_cleared_state(self) -> None:
        mock_agent = Mock()

        existing_state = {
            "schemaVersion": "1.0.0",
            "data": {
                "conversationHistory": [
                    {
                        "$type": "request",
                        "correlationId": "corr-existing-1",
                        "createdAt": "2024-01-01T00:00:00Z",
                        "messages": [{"role": "user", "contents": [{"$type": "text", "text": "msg1"}]}],
                    }
                ]
            },
        }

        entity, ctx = self._make_durabletask_entity_provider(mock_agent, initial_state=existing_state)

        entity.reset()

        persisted = ctx.get_state(dict, default={})
        assert isinstance(persisted, dict)
        assert persisted["data"]["conversationHistory"] == []


class TestAgentEntityRunAgent:
    """Test suite for the run_agent operation."""

    async def test_run_executes_agent(self) -> None:
        """Test that run executes the agent."""
        mock_agent = Mock()
        mock_response = _agent_response("Test response")
        mock_agent.run = AsyncMock(return_value=mock_response)

        entity = _make_entity(mock_agent)

        result = await entity.run({
            "message": "Test message",
            "correlationId": "corr-entity-1",
        })

        # Verify agent.run was called
        mock_agent.run.assert_called_once()
        _, kwargs = mock_agent.run.call_args
        sent_messages: list[Any] = kwargs.get("messages")
        assert len(sent_messages) == 1
        sent_message = sent_messages[0]
        assert isinstance(sent_message, ChatMessage)
        assert getattr(sent_message, "text", None) == "Test message"
        assert getattr(sent_message.role, "value", sent_message.role) == "user"

        # Verify result
        assert isinstance(result, AgentResponse)
        assert result.text == "Test response"

    async def test_run_agent_streaming_callbacks_invoked(self) -> None:
        """Ensure streaming updates trigger callbacks and run() is not used."""
        updates = [
            AgentResponseUpdate(text="Hello"),
            AgentResponseUpdate(text=" world"),
        ]

        async def update_generator() -> AsyncIterator[AgentResponseUpdate]:
            for update in updates:
                yield update

        mock_agent = Mock()
        mock_agent.name = "StreamingAgent"
        mock_agent.run_stream = Mock(return_value=update_generator())
        mock_agent.run = AsyncMock(side_effect=AssertionError("run() should not be called when streaming succeeds"))

        callback = RecordingCallback()
        entity = _make_entity(mock_agent, callback=callback, thread_id="session-1")

        result = await entity.run(
            {
                "message": "Tell me something",
                "correlationId": "corr-stream-1",
            },
        )

        assert isinstance(result, AgentResponse)
        assert "Hello" in result.text
        assert callback.stream_mock.await_count == len(updates)
        assert callback.response_mock.await_count == 1
        mock_agent.run.assert_not_called()

        # Validate callback arguments
        stream_calls = callback.stream_mock.await_args_list
        for expected_update, recorded_call in zip(updates, stream_calls, strict=True):
            assert recorded_call.args[0] is expected_update
            context = recorded_call.args[1]
            assert context.agent_name == "StreamingAgent"
            assert context.correlation_id == "corr-stream-1"
            assert context.thread_id == "session-1"
            assert context.request_message == "Tell me something"

        final_call = callback.response_mock.await_args
        assert final_call is not None
        final_response, final_context = final_call.args
        assert final_context.agent_name == "StreamingAgent"
        assert final_context.correlation_id == "corr-stream-1"
        assert final_context.thread_id == "session-1"
        assert final_context.request_message == "Tell me something"
        assert getattr(final_response, "text", "").strip()

    async def test_run_agent_final_callback_without_streaming(self) -> None:
        """Ensure the final callback fires even when streaming is unavailable."""
        mock_agent = Mock()
        mock_agent.name = "NonStreamingAgent"
        mock_agent.run_stream = None
        agent_response = _agent_response("Final response")
        mock_agent.run = AsyncMock(return_value=agent_response)

        callback = RecordingCallback()
        entity = _make_entity(mock_agent, callback=callback, thread_id="session-2")

        result = await entity.run(
            {
                "message": "Hi",
                "correlationId": "corr-final-1",
            },
        )

        assert isinstance(result, AgentResponse)
        assert result.text == "Final response"
        assert callback.stream_mock.await_count == 0
        assert callback.response_mock.await_count == 1

        final_call = callback.response_mock.await_args
        assert final_call is not None
        assert final_call.args[0] is agent_response
        final_context = final_call.args[1]
        assert final_context.agent_name == "NonStreamingAgent"
        assert final_context.correlation_id == "corr-final-1"
        assert final_context.thread_id == "session-2"
        assert final_context.request_message == "Hi"

    async def test_run_agent_updates_conversation_history(self) -> None:
        """Test that run_agent updates the conversation history."""
        mock_agent = Mock()
        mock_response = _agent_response("Agent response")
        mock_agent.run = AsyncMock(return_value=mock_response)

        entity = _make_entity(mock_agent)

        await entity.run({"message": "User message", "correlationId": "corr-entity-2"})

        # Should have 2 entries: user message + assistant response
        user_history = entity.state.data.conversation_history[0].messages
        assistant_history = entity.state.data.conversation_history[1].messages

        assert len(user_history) == 1

        user_msg = user_history[0]
        assert _role_value(user_msg) == "user"
        assert user_msg.text == "User message"

        assistant_msg = assistant_history[0]
        assert _role_value(assistant_msg) == "assistant"
        assert assistant_msg.text == "Agent response"

    async def test_run_agent_increments_message_count(self) -> None:
        """Test that run_agent increments the message count."""
        mock_agent = Mock()
        mock_agent.run = AsyncMock(return_value=_agent_response("Response"))

        entity = _make_entity(mock_agent)

        assert len(entity.state.data.conversation_history) == 0

        await entity.run({"message": "Message 1", "correlationId": "corr-entity-3a"})
        assert len(entity.state.data.conversation_history) == 2

        await entity.run({"message": "Message 2", "correlationId": "corr-entity-3b"})
        assert len(entity.state.data.conversation_history) == 4

        await entity.run({"message": "Message 3", "correlationId": "corr-entity-3c"})
        assert len(entity.state.data.conversation_history) == 6

    async def test_run_requires_entity_thread_id(self) -> None:
        """Test that AgentEntity.run rejects missing entity thread identifiers."""
        mock_agent = Mock()
        mock_agent.run = AsyncMock(return_value=_agent_response("Response"))

        entity = _make_entity(mock_agent, thread_id="")

        with pytest.raises(ValueError, match="thread_id"):
            await entity.run({"message": "Message", "correlationId": "corr-entity-5"})

    async def test_run_agent_multiple_conversations(self) -> None:
        """Test that run_agent maintains history across multiple messages."""
        mock_agent = Mock()
        mock_agent.run = AsyncMock(return_value=_agent_response("Response"))

        entity = _make_entity(mock_agent)

        # Send multiple messages
        await entity.run({"message": "Message 1", "correlationId": "corr-entity-8a"})
        await entity.run({"message": "Message 2", "correlationId": "corr-entity-8b"})
        await entity.run({"message": "Message 3", "correlationId": "corr-entity-8c"})

        history = entity.state.data.conversation_history
        assert len(history) == 6
        assert entity.state.message_count == 6


class TestAgentEntityReset:
    """Test suite for the reset operation."""

    def test_reset_clears_conversation_history(self) -> None:
        """Test that reset clears the conversation history."""
        mock_agent = Mock()
        entity = _make_entity(mock_agent)

        # Add some history with proper DurableAgentStateEntry objects
        entity.state.data.conversation_history = [
            DurableAgentStateRequest(
                correlation_id="test-1",
                created_at=datetime.now(),
                messages=[
                    DurableAgentStateMessage(
                        role="user",
                        contents=[DurableAgentStateTextContent(text="msg1")],
                    )
                ],
            ),
        ]

        entity.reset()

        assert entity.state.data.conversation_history == []

    def test_reset_with_extension_data(self) -> None:
        """Test that reset works when entity has extension data."""
        mock_agent = Mock()
        entity = _make_entity(mock_agent)

        # Set up some initial state with conversation history
        entity.state.data = DurableAgentStateData(conversation_history=[], extension_data={"some_key": "some_value"})

        entity.reset()

        assert len(entity.state.data.conversation_history) == 0

    def test_reset_clears_message_count(self) -> None:
        """Test that reset clears the message count."""
        mock_agent = Mock()
        entity = _make_entity(mock_agent)

        entity.reset()

        assert len(entity.state.data.conversation_history) == 0

    async def test_reset_after_conversation(self) -> None:
        """Test reset after a full conversation."""
        mock_agent = Mock()
        mock_agent.run = AsyncMock(return_value=_agent_response("Response"))

        entity = _make_entity(mock_agent)

        # Have a conversation
        await entity.run({"message": "Message 1", "correlationId": "corr-entity-10a"})
        await entity.run({"message": "Message 2", "correlationId": "corr-entity-10b"})

        # Verify state before reset
        assert entity.state.message_count == 4
        assert len(entity.state.data.conversation_history) == 4

        # Reset
        entity.reset()

        # Verify state after reset
        assert entity.state.message_count == 0
        assert len(entity.state.data.conversation_history) == 0


class TestErrorHandling:
    """Test suite for error handling in entities."""

    async def test_run_agent_handles_agent_exception(self) -> None:
        """Test that run_agent handles agent exceptions."""
        mock_agent = Mock()
        mock_agent.run = AsyncMock(side_effect=Exception("Agent failed"))

        entity = _make_entity(mock_agent)

        result = await entity.run({"message": "Message", "correlationId": "corr-entity-error-1"})

        assert isinstance(result, AgentResponse)
        assert len(result.messages) == 1
        content = result.messages[0].contents[0]
        assert isinstance(content, Content)
        assert "Agent failed" in (content.message or "")
        assert content.error_code == "Exception"

    async def test_run_agent_handles_value_error(self) -> None:
        """Test that run_agent handles ValueError instances."""
        mock_agent = Mock()
        mock_agent.run = AsyncMock(side_effect=ValueError("Invalid input"))

        entity = _make_entity(mock_agent)

        result = await entity.run({"message": "Message", "correlationId": "corr-entity-error-2"})

        assert isinstance(result, AgentResponse)
        assert len(result.messages) == 1
        content = result.messages[0].contents[0]
        assert isinstance(content, Content)
        assert content.error_code == "ValueError"
        assert "Invalid input" in str(content.message)

    async def test_run_agent_handles_timeout_error(self) -> None:
        """Test that run_agent handles TimeoutError instances."""
        mock_agent = Mock()
        mock_agent.run = AsyncMock(side_effect=TimeoutError("Request timeout"))

        entity = _make_entity(mock_agent)

        result = await entity.run({"message": "Message", "correlationId": "corr-entity-error-3"})

        assert isinstance(result, AgentResponse)
        assert len(result.messages) == 1
        content = result.messages[0].contents[0]
        assert isinstance(content, Content)
        assert content.error_code == "TimeoutError"

    async def test_run_agent_preserves_message_on_error(self) -> None:
        """Test that run_agent preserves message information on error."""
        mock_agent = Mock()
        mock_agent.run = AsyncMock(side_effect=Exception("Error"))

        entity = _make_entity(mock_agent)

        result = await entity.run(
            {"message": "Test message", "correlationId": "corr-entity-error-4"},
        )

        # Even on error, message info should be preserved
        assert isinstance(result, AgentResponse)
        assert len(result.messages) == 1
        content = result.messages[0].contents[0]
        assert isinstance(content, Content)


class TestConversationHistory:
    """Test suite for conversation history tracking."""

    async def test_conversation_history_has_timestamps(self) -> None:
        """Test that conversation history entries include timestamps."""
        mock_agent = Mock()
        mock_agent.run = AsyncMock(return_value=_agent_response("Response"))

        entity = _make_entity(mock_agent)

        await entity.run({"message": "Message", "correlationId": "corr-entity-history-1"})

        # Check both user and assistant messages have timestamps
        for entry in entity.state.data.conversation_history:
            timestamp = entry.created_at
            assert timestamp is not None
            # Verify timestamp is in ISO format
            datetime.fromisoformat(str(timestamp))

    async def test_conversation_history_ordering(self) -> None:
        """Test that conversation history maintains the correct order."""
        mock_agent = Mock()

        entity = _make_entity(mock_agent)

        # Send multiple messages with different responses
        mock_agent.run = AsyncMock(return_value=_agent_response("Response 1"))
        await entity.run(
            {"message": "Message 1", "correlationId": "corr-entity-history-2a"},
        )

        mock_agent.run = AsyncMock(return_value=_agent_response("Response 2"))
        await entity.run(
            {"message": "Message 2", "correlationId": "corr-entity-history-2b"},
        )

        mock_agent.run = AsyncMock(return_value=_agent_response("Response 3"))
        await entity.run(
            {"message": "Message 3", "correlationId": "corr-entity-history-2c"},
        )

        # Verify order
        history = entity.state.data.conversation_history
        # Each conversation turn creates 2 entries: request and response
        assert history[0].messages[0].text == "Message 1"  # Request 1
        assert history[1].messages[0].text == "Response 1"  # Response 1
        assert history[2].messages[0].text == "Message 2"  # Request 2
        assert history[3].messages[0].text == "Response 2"  # Response 2
        assert history[4].messages[0].text == "Message 3"  # Request 3
        assert history[5].messages[0].text == "Response 3"  # Response 3

    async def test_conversation_history_role_alternation(self) -> None:
        """Test that conversation history alternates between user and assistant roles."""
        mock_agent = Mock()
        mock_agent.run = AsyncMock(return_value=_agent_response("Response"))

        entity = _make_entity(mock_agent)

        await entity.run(
            {"message": "Message 1", "correlationId": "corr-entity-history-3a"},
        )
        await entity.run(
            {"message": "Message 2", "correlationId": "corr-entity-history-3b"},
        )

        # Check role alternation
        history = entity.state.data.conversation_history
        # Each conversation turn creates 2 entries: request and response
        assert history[0].messages[0].role == "user"  # Request 1
        assert history[1].messages[0].role == "assistant"  # Response 1
        assert history[2].messages[0].role == "user"  # Request 2
        assert history[3].messages[0].role == "assistant"  # Response 2


class TestRunRequestSupport:
    """Test suite for RunRequest support in entities."""

    async def test_run_agent_with_run_request_object(self) -> None:
        """Test run_agent with a RunRequest object."""
        mock_agent = Mock()
        mock_agent.run = AsyncMock(return_value=_agent_response("Response"))

        entity = _make_entity(mock_agent)

        request = RunRequest(
            message="Test message",
            role=Role.USER,
            enable_tool_calls=True,
            correlation_id="corr-runreq-1",
        )

        result = await entity.run(request)

        assert isinstance(result, AgentResponse)
        assert result.text == "Response"

    async def test_run_agent_with_dict_request(self) -> None:
        """Test run_agent with a dictionary request."""
        mock_agent = Mock()
        mock_agent.run = AsyncMock(return_value=_agent_response("Response"))

        entity = _make_entity(mock_agent)

        request_dict = {
            "message": "Test message",
            "role": "system",
            "enable_tool_calls": False,
            "correlationId": "corr-runreq-2",
        }

        result = await entity.run(request_dict)

        assert isinstance(result, AgentResponse)
        assert result.text == "Response"

    async def test_run_agent_with_string_raises_without_correlation(self) -> None:
        """Test that run_agent rejects legacy string input without correlation ID."""
        mock_agent = Mock()
        mock_agent.run = AsyncMock(return_value=_agent_response("Response"))

        entity = _make_entity(mock_agent)

        with pytest.raises(ValueError):
            await entity.run("Simple message")

    async def test_run_agent_stores_role_in_history(self) -> None:
        """Test that run_agent stores the role in conversation history."""
        mock_agent = Mock()
        mock_agent.run = AsyncMock(return_value=_agent_response("Response"))

        entity = _make_entity(mock_agent)

        # Send as system role
        request = RunRequest(
            message="System message",
            role=Role.SYSTEM,
            correlation_id="corr-runreq-3",
        )

        await entity.run(request)

        # Check that system role was stored
        history = entity.state.data.conversation_history
        assert history[0].messages[0].role == "system"
        assert history[0].messages[0].text == "System message"

    async def test_run_agent_with_response_format(self) -> None:
        """Test run_agent with a JSON response format."""
        mock_agent = Mock()
        # Return JSON response
        mock_agent.run = AsyncMock(return_value=_agent_response('{"answer": 42}'))

        entity = _make_entity(mock_agent)

        request = RunRequest(
            message="What is the answer?",
            response_format=EntityStructuredResponse,
            correlation_id="corr-runreq-4",
        )

        result = await entity.run(request)

        assert isinstance(result, AgentResponse)
        assert result.text == '{"answer": 42}'
        assert result.value is None

    async def test_run_agent_disable_tool_calls(self) -> None:
        """Test run_agent with tool calls disabled."""
        mock_agent = Mock()
        mock_agent.run = AsyncMock(return_value=_agent_response("Response"))

        entity = _make_entity(mock_agent)

        request = RunRequest(message="Test", enable_tool_calls=False, correlation_id="corr-runreq-5")

        result = await entity.run(request)

        assert isinstance(result, AgentResponse)
        # Agent should have been called (tool disabling is framework-dependent)
        mock_agent.run.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
