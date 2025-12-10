# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for AgentEntity and entity operations.

Run with: pytest tests/test_entities.py -v
"""

import asyncio
from collections.abc import AsyncIterator, Callable
from datetime import datetime
from typing import Any, TypeVar
from unittest.mock import AsyncMock, Mock, patch

import pytest
from agent_framework import AgentRunResponse, AgentRunResponseUpdate, ChatMessage, ErrorContent, Role
from pydantic import BaseModel

from agent_framework_azurefunctions._durable_agent_state import (
    DurableAgentState,
    DurableAgentStateData,
    DurableAgentStateMessage,
    DurableAgentStateRequest,
    DurableAgentStateTextContent,
)
from agent_framework_azurefunctions._entities import AgentEntity, create_agent_entity
from agent_framework_azurefunctions._models import RunRequest

TFunc = TypeVar("TFunc", bound=Callable[..., Any])


def _role_value(chat_message: DurableAgentStateMessage) -> str:
    """Helper to extract the string role from a ChatMessage."""
    role = getattr(chat_message, "role", None)
    role_value = getattr(role, "value", role)
    if role_value is None:
        return ""
    return str(role_value)


def _agent_response(text: str | None) -> AgentRunResponse:
    """Create an AgentRunResponse with a single assistant message."""
    message = (
        ChatMessage(role="assistant", text=text) if text is not None else ChatMessage(role="assistant", contents=[])
    )
    return AgentRunResponse(messages=[message])


class RecordingCallback:
    """Callback implementation capturing streaming and final responses for assertions."""

    def __init__(self):
        self.stream_mock = AsyncMock()
        self.response_mock = AsyncMock()

    async def on_streaming_response_update(
        self,
        update: AgentRunResponseUpdate,
        context: Any,
    ) -> None:
        await self.stream_mock(update, context)

    async def on_agent_response(self, response: AgentRunResponse, context: Any) -> None:
        await self.response_mock(response, context)


class EntityStructuredResponse(BaseModel):
    answer: float


class TestAgentEntityInit:
    """Test suite for AgentEntity initialization."""

    def test_init_creates_entity(self) -> None:
        """Test that AgentEntity initializes correctly."""
        mock_agent = Mock()

        entity = AgentEntity(mock_agent)

        assert entity.agent == mock_agent
        assert len(entity.state.data.conversation_history) == 0
        assert entity.state.data.extension_data is None
        assert entity.state.schema_version == DurableAgentState.SCHEMA_VERSION

    def test_init_stores_agent_reference(self) -> None:
        """Test that the agent reference is stored correctly."""
        mock_agent = Mock()
        mock_agent.name = "TestAgent"

        entity = AgentEntity(mock_agent)

        assert entity.agent.name == "TestAgent"

    def test_init_with_different_agent_types(self) -> None:
        """Test initialization with different agent types."""
        agent1 = Mock()
        agent1.__class__.__name__ = "AzureOpenAIAgent"

        agent2 = Mock()
        agent2.__class__.__name__ = "CustomAgent"

        entity1 = AgentEntity(agent1)
        entity2 = AgentEntity(agent2)

        assert entity1.agent.__class__.__name__ == "AzureOpenAIAgent"
        assert entity2.agent.__class__.__name__ == "CustomAgent"


class TestAgentEntityRunAgent:
    """Test suite for the run_agent operation."""

    async def test_run_agent_executes_agent(self) -> None:
        """Test that run_agent executes the agent."""
        mock_agent = Mock()
        mock_response = _agent_response("Test response")
        mock_agent.run = AsyncMock(return_value=mock_response)

        entity = AgentEntity(mock_agent)
        mock_context = Mock()

        result = await entity.run_agent(
            mock_context, {"message": "Test message", "thread_id": "conv-123", "correlationId": "corr-entity-1"}
        )

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
        assert isinstance(result, AgentRunResponse)
        assert result.text == "Test response"

    async def test_run_agent_streaming_callbacks_invoked(self) -> None:
        """Ensure streaming updates trigger callbacks and run() is not used."""

        updates = [
            AgentRunResponseUpdate(text="Hello"),
            AgentRunResponseUpdate(text=" world"),
        ]

        async def update_generator() -> AsyncIterator[AgentRunResponseUpdate]:
            for update in updates:
                yield update

        mock_agent = Mock()
        mock_agent.name = "StreamingAgent"
        mock_agent.run_stream = Mock(return_value=update_generator())
        mock_agent.run = AsyncMock(side_effect=AssertionError("run() should not be called when streaming succeeds"))

        callback = RecordingCallback()
        entity = AgentEntity(mock_agent, callback=callback)
        mock_context = Mock()

        result = await entity.run_agent(
            mock_context,
            {
                "message": "Tell me something",
                "thread_id": "session-1",
                "correlationId": "corr-stream-1",
            },
        )

        assert isinstance(result, AgentRunResponse)
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
        entity = AgentEntity(mock_agent, callback=callback)
        mock_context = Mock()

        result = await entity.run_agent(
            mock_context,
            {
                "message": "Hi",
                "thread_id": "session-2",
                "correlationId": "corr-final-1",
            },
        )

        assert isinstance(result, AgentRunResponse)
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

        entity = AgentEntity(mock_agent)
        mock_context = Mock()

        await entity.run_agent(
            mock_context, {"message": "User message", "thread_id": "conv-1", "correlationId": "corr-entity-2"}
        )

        # Should have 1 entry: user message + assistant response
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

        entity = AgentEntity(mock_agent)
        mock_context = Mock()

        assert len(entity.state.data.conversation_history) == 0

        await entity.run_agent(
            mock_context, {"message": "Message 1", "thread_id": "conv-1", "correlationId": "corr-entity-3a"}
        )
        assert len(entity.state.data.conversation_history) == 2

        await entity.run_agent(
            mock_context, {"message": "Message 2", "thread_id": "conv-1", "correlationId": "corr-entity-3b"}
        )
        assert len(entity.state.data.conversation_history) == 4

        await entity.run_agent(
            mock_context, {"message": "Message 3", "thread_id": "conv-1", "correlationId": "corr-entity-3c"}
        )
        assert len(entity.state.data.conversation_history) == 6

    async def test_run_agent_with_none_thread_id(self) -> None:
        """Test run_agent with a None thread identifier."""
        mock_agent = Mock()
        mock_agent.run = AsyncMock(return_value=_agent_response("Response"))

        entity = AgentEntity(mock_agent)
        mock_context = Mock()

        with pytest.raises(ValueError, match="thread_id"):
            await entity.run_agent(
                mock_context, {"message": "Message", "thread_id": None, "correlationId": "corr-entity-5"}
            )

    async def test_run_agent_multiple_conversations(self) -> None:
        """Test that run_agent maintains history across multiple messages."""
        mock_agent = Mock()
        mock_agent.run = AsyncMock(return_value=_agent_response("Response"))

        entity = AgentEntity(mock_agent)
        mock_context = Mock()

        # Send multiple messages
        await entity.run_agent(
            mock_context, {"message": "Message 1", "thread_id": "conv-1", "correlationId": "corr-entity-8a"}
        )
        await entity.run_agent(
            mock_context, {"message": "Message 2", "thread_id": "conv-1", "correlationId": "corr-entity-8b"}
        )
        await entity.run_agent(
            mock_context, {"message": "Message 3", "thread_id": "conv-1", "correlationId": "corr-entity-8c"}
        )

        history = entity.state.data.conversation_history
        assert len(history) == 6
        assert entity.state.message_count == 6


class TestAgentEntityReset:
    """Test suite for the reset operation."""

    def test_reset_clears_conversation_history(self) -> None:
        """Test that reset clears the conversation history."""
        mock_agent = Mock()
        entity = AgentEntity(mock_agent)

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

        mock_context = Mock()
        entity.reset(mock_context)

        assert entity.state.data.conversation_history == []

    def test_reset_with_extension_data(self) -> None:
        """Test that reset works when entity has extension data."""
        mock_agent = Mock()
        entity = AgentEntity(mock_agent)

        # Set up some initial state with conversation history
        entity.state.data = DurableAgentStateData(conversation_history=[], extension_data={"some_key": "some_value"})

        mock_context = Mock()
        entity.reset(mock_context)

        assert len(entity.state.data.conversation_history) == 0

    def test_reset_clears_message_count(self) -> None:
        """Test that reset clears the message count."""
        mock_agent = Mock()
        entity = AgentEntity(mock_agent)

        mock_context = Mock()
        entity.reset(mock_context)

        assert len(entity.state.data.conversation_history) == 0

    async def test_reset_after_conversation(self) -> None:
        """Test reset after a full conversation."""
        mock_agent = Mock()
        mock_agent.run = AsyncMock(return_value=_agent_response("Response"))

        entity = AgentEntity(mock_agent)
        mock_context = Mock()

        # Have a conversation
        await entity.run_agent(
            mock_context, {"message": "Message 1", "thread_id": "conv-1", "correlationId": "corr-entity-10a"}
        )
        await entity.run_agent(
            mock_context, {"message": "Message 2", "thread_id": "conv-1", "correlationId": "corr-entity-10b"}
        )

        # Verify state before reset
        assert entity.state.message_count == 4
        assert len(entity.state.data.conversation_history) == 4

        # Reset
        entity.reset(mock_context)

        # Verify state after reset
        assert entity.state.message_count == 0
        assert len(entity.state.data.conversation_history) == 0


class TestCreateAgentEntity:
    """Test suite for the create_agent_entity factory function."""

    def test_create_agent_entity_returns_callable(self) -> None:
        """Test that create_agent_entity returns a callable."""
        mock_agent = Mock()

        entity_function = create_agent_entity(mock_agent)

        assert callable(entity_function)

    def test_entity_function_handles_run_agent(self) -> None:
        """Test that the entity function handles the run_agent operation."""
        mock_agent = Mock()
        mock_agent.run = AsyncMock(return_value=_agent_response("Response"))

        entity_function = create_agent_entity(mock_agent)

        # Mock context
        mock_context = Mock()
        mock_context.operation_name = "run_agent"
        mock_context.get_input.return_value = {
            "message": "Test message",
            "thread_id": "conv-123",
            "correlationId": "corr-entity-factory",
        }
        mock_context.get_state.return_value = None

        # Execute
        entity_function(mock_context)

        # Verify result and state were set
        assert mock_context.set_result.called
        assert mock_context.set_state.called

    def test_entity_function_handles_reset(self) -> None:
        """Test that the entity function handles the reset operation."""
        mock_agent = Mock()

        entity_function = create_agent_entity(mock_agent)

        # Mock context with existing state
        mock_context = Mock()
        mock_context.operation_name = "reset"
        mock_context.get_state.return_value = {
            "schemaVersion": "1.0.0",
            "data": {
                "conversationHistory": [
                    {
                        "$type": "request",
                        "correlationId": "test-correlation-id",
                        "createdAt": "2024-01-01T00:00:00Z",
                        "messages": [
                            {
                                "role": "user",
                                "contents": [{"$type": "text", "text": "test"}],
                            }
                        ],
                    }
                ]
            },
        }

        # Execute
        entity_function(mock_context)

        # Verify reset result
        assert mock_context.set_result.called
        result = mock_context.set_result.call_args[0][0]
        assert result["status"] == "reset"

        # Verify state was cleared
        assert mock_context.set_state.called
        state = mock_context.set_state.call_args[0][0]
        assert state["data"]["conversationHistory"] == []

    def test_entity_function_handles_unknown_operation(self) -> None:
        """Test that the entity function handles unknown operations."""
        mock_agent = Mock()

        entity_function = create_agent_entity(mock_agent)

        mock_context = Mock()
        mock_context.operation_name = "invalid_operation"
        mock_context.get_state.return_value = None

        # Execute
        entity_function(mock_context)

        # Verify error result
        assert mock_context.set_result.called
        result = mock_context.set_result.call_args[0][0]
        assert "error" in result
        assert "invalid_operation" in result["error"].lower()

    def test_entity_function_creates_new_entity_on_first_call(self) -> None:
        """Test that the entity function creates a new entity when no state exists."""
        mock_agent = Mock()
        mock_agent.__class__.__name__ = "Agent"

        entity_function = create_agent_entity(mock_agent)
        mock_context = Mock()
        mock_context.operation_name = "reset"
        mock_context.get_state.return_value = None  # No existing state

        # Execute
        entity_function(mock_context)

        # Verify new entity state was created
        assert mock_context.set_result.called
        result = mock_context.set_result.call_args[0][0]
        assert result["status"] == "reset"
        assert mock_context.set_state.called
        state = mock_context.set_state.call_args[0][0]
        assert state["data"] == {"conversationHistory": []}

    def test_entity_function_restores_existing_state(self) -> None:
        """Test that the entity function restores existing state."""
        mock_agent = Mock()

        entity_function = create_agent_entity(mock_agent)

        existing_state = {
            "schemaVersion": "1.0.0",
            "data": {
                "conversationHistory": [
                    {
                        "$type": "request",
                        "correlationId": "corr-existing-1",
                        "createdAt": "2024-01-01T00:00:00Z",
                        "messages": [
                            {
                                "role": "user",
                                "contents": [
                                    {
                                        "$type": "text",
                                        "text": "msg1",
                                    }
                                ],
                            }
                        ],
                    },
                    {
                        "$type": "response",
                        "correlationId": "corr-existing-1",
                        "createdAt": "2024-01-01T00:05:00Z",
                        "messages": [
                            {
                                "role": "assistant",
                                "contents": [
                                    {
                                        "$type": "text",
                                        "text": "resp1",
                                    }
                                ],
                            }
                        ],
                    },
                ],
            },
        }

        mock_context = Mock()
        mock_context.operation_name = "reset"
        mock_context.get_state.return_value = existing_state

        with patch.object(DurableAgentState, "from_dict", wraps=DurableAgentState.from_dict) as from_dict_mock:
            entity_function(mock_context)

        from_dict_mock.assert_called_once_with(existing_state)


class TestErrorHandling:
    """Test suite for error handling in entities."""

    async def test_run_agent_handles_agent_exception(self) -> None:
        """Test that run_agent handles agent exceptions."""
        mock_agent = Mock()
        mock_agent.run = AsyncMock(side_effect=Exception("Agent failed"))

        entity = AgentEntity(mock_agent)
        mock_context = Mock()

        result = await entity.run_agent(
            mock_context, {"message": "Message", "thread_id": "conv-1", "correlationId": "corr-entity-error-1"}
        )

        assert isinstance(result, AgentRunResponse)
        assert len(result.messages) == 1
        content = result.messages[0].contents[0]
        assert isinstance(content, ErrorContent)
        assert "Agent failed" in (content.message or "")
        assert content.error_code == "Exception"

    async def test_run_agent_handles_value_error(self) -> None:
        """Test that run_agent handles ValueError instances."""
        mock_agent = Mock()
        mock_agent.run = AsyncMock(side_effect=ValueError("Invalid input"))

        entity = AgentEntity(mock_agent)
        mock_context = Mock()

        result = await entity.run_agent(
            mock_context, {"message": "Message", "thread_id": "conv-1", "correlationId": "corr-entity-error-2"}
        )

        assert isinstance(result, AgentRunResponse)
        assert len(result.messages) == 1
        content = result.messages[0].contents[0]
        assert isinstance(content, ErrorContent)
        assert content.error_code == "ValueError"
        assert "Invalid input" in str(content.message)

    async def test_run_agent_handles_timeout_error(self) -> None:
        """Test that run_agent handles TimeoutError instances."""
        mock_agent = Mock()
        mock_agent.run = AsyncMock(side_effect=TimeoutError("Request timeout"))

        entity = AgentEntity(mock_agent)
        mock_context = Mock()

        result = await entity.run_agent(
            mock_context, {"message": "Message", "thread_id": "conv-1", "correlationId": "corr-entity-error-3"}
        )

        assert isinstance(result, AgentRunResponse)
        assert len(result.messages) == 1
        content = result.messages[0].contents[0]
        assert isinstance(content, ErrorContent)
        assert content.error_code == "TimeoutError"

    def test_entity_function_handles_exception_in_operation(self) -> None:
        """Test that the entity function handles exceptions gracefully."""
        mock_agent = Mock()

        entity_function = create_agent_entity(mock_agent)

        mock_context = Mock()
        mock_context.operation_name = "run_agent"
        mock_context.get_input.side_effect = Exception("Input error")
        mock_context.get_state.return_value = None

        # Execute - should not raise
        entity_function(mock_context)

        # Verify error was set
        assert mock_context.set_result.called
        result = mock_context.set_result.call_args[0][0]
        assert "error" in result

    async def test_run_agent_preserves_message_on_error(self) -> None:
        """Test that run_agent preserves message information on error."""
        mock_agent = Mock()
        mock_agent.run = AsyncMock(side_effect=Exception("Error"))

        entity = AgentEntity(mock_agent)
        mock_context = Mock()

        result = await entity.run_agent(
            mock_context,
            {"message": "Test message", "thread_id": "conv-123", "correlationId": "corr-entity-error-4"},
        )

        # Even on error, message info should be preserved
        assert isinstance(result, AgentRunResponse)
        assert len(result.messages) == 1
        content = result.messages[0].contents[0]
        assert isinstance(content, ErrorContent)


class TestConversationHistory:
    """Test suite for conversation history tracking."""

    async def test_conversation_history_has_timestamps(self) -> None:
        """Test that conversation history entries include timestamps."""
        mock_agent = Mock()
        mock_agent.run = AsyncMock(return_value=_agent_response("Response"))

        entity = AgentEntity(mock_agent)
        mock_context = Mock()

        await entity.run_agent(
            mock_context, {"message": "Message", "thread_id": "conv-1", "correlationId": "corr-entity-history-1"}
        )

        # Check both user and assistant messages have timestamps
        for entry in entity.state.data.conversation_history:
            timestamp = entry.created_at
            assert timestamp is not None
            # Verify timestamp is in ISO format
            datetime.fromisoformat(str(timestamp))

    async def test_conversation_history_ordering(self) -> None:
        """Test that conversation history maintains the correct order."""
        mock_agent = Mock()

        entity = AgentEntity(mock_agent)
        mock_context = Mock()

        # Send multiple messages with different responses
        mock_agent.run = AsyncMock(return_value=_agent_response("Response 1"))
        await entity.run_agent(
            mock_context,
            {"message": "Message 1", "thread_id": "conv-1", "correlationId": "corr-entity-history-2a"},
        )

        mock_agent.run = AsyncMock(return_value=_agent_response("Response 2"))
        await entity.run_agent(
            mock_context,
            {"message": "Message 2", "thread_id": "conv-1", "correlationId": "corr-entity-history-2b"},
        )

        mock_agent.run = AsyncMock(return_value=_agent_response("Response 3"))
        await entity.run_agent(
            mock_context,
            {"message": "Message 3", "thread_id": "conv-1", "correlationId": "corr-entity-history-2c"},
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

        entity = AgentEntity(mock_agent)
        mock_context = Mock()

        await entity.run_agent(
            mock_context,
            {"message": "Message 1", "thread_id": "conv-1", "correlationId": "corr-entity-history-3a"},
        )
        await entity.run_agent(
            mock_context,
            {"message": "Message 2", "thread_id": "conv-1", "correlationId": "corr-entity-history-3b"},
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

        entity = AgentEntity(mock_agent)
        mock_context = Mock()

        request = RunRequest(
            message="Test message",
            thread_id="conv-123",
            role=Role.USER,
            enable_tool_calls=True,
            correlation_id="corr-runreq-1",
        )

        result = await entity.run_agent(mock_context, request)

        assert isinstance(result, AgentRunResponse)
        assert result.text == "Response"

    async def test_run_agent_with_dict_request(self) -> None:
        """Test run_agent with a dictionary request."""
        mock_agent = Mock()
        mock_agent.run = AsyncMock(return_value=_agent_response("Response"))

        entity = AgentEntity(mock_agent)
        mock_context = Mock()

        request_dict = {
            "message": "Test message",
            "thread_id": "conv-456",
            "role": "system",
            "enable_tool_calls": False,
            "correlationId": "corr-runreq-2",
        }

        result = await entity.run_agent(mock_context, request_dict)

        assert isinstance(result, AgentRunResponse)
        assert result.text == "Response"

    async def test_run_agent_with_string_raises_without_correlation(self) -> None:
        """Test that run_agent rejects legacy string input without correlation ID."""
        mock_agent = Mock()
        mock_agent.run = AsyncMock(return_value=_agent_response("Response"))

        entity = AgentEntity(mock_agent)
        mock_context = Mock()

        with pytest.raises(ValueError):
            await entity.run_agent(mock_context, "Simple message")

    async def test_run_agent_stores_role_in_history(self) -> None:
        """Test that run_agent stores the role in conversation history."""
        mock_agent = Mock()
        mock_agent.run = AsyncMock(return_value=_agent_response("Response"))

        entity = AgentEntity(mock_agent)
        mock_context = Mock()

        # Send as system role
        request = RunRequest(
            message="System message",
            thread_id="conv-runreq-3",
            role=Role.SYSTEM,
            correlation_id="corr-runreq-3",
        )

        await entity.run_agent(mock_context, request)

        # Check that system role was stored
        history = entity.state.data.conversation_history
        assert history[0].messages[0].role == "system"
        assert history[0].messages[0].text == "System message"

    async def test_run_agent_with_response_format(self) -> None:
        """Test run_agent with a JSON response format."""
        mock_agent = Mock()
        # Return JSON response
        mock_agent.run = AsyncMock(return_value=_agent_response('{"answer": 42}'))

        entity = AgentEntity(mock_agent)
        mock_context = Mock()

        request = RunRequest(
            message="What is the answer?",
            thread_id="conv-runreq-4",
            response_format=EntityStructuredResponse,
            correlation_id="corr-runreq-4",
        )

        result = await entity.run_agent(mock_context, request)

        assert isinstance(result, AgentRunResponse)
        assert result.text == '{"answer": 42}'
        assert result.value is None

    async def test_run_agent_disable_tool_calls(self) -> None:
        """Test run_agent with tool calls disabled."""
        mock_agent = Mock()
        mock_agent.run = AsyncMock(return_value=_agent_response("Response"))

        entity = AgentEntity(mock_agent)
        mock_context = Mock()

        request = RunRequest(
            message="Test", thread_id="conv-runreq-5", enable_tool_calls=False, correlation_id="corr-runreq-5"
        )

        result = await entity.run_agent(mock_context, request)

        assert isinstance(result, AgentRunResponse)
        # Agent should have been called (tool disabling is framework-dependent)
        mock_agent.run.assert_called_once()

    async def test_entity_function_with_run_request_dict(self) -> None:
        """Test that the entity function handles the RunRequest dict format."""
        mock_agent = Mock()
        mock_agent.run = AsyncMock(return_value=_agent_response("Response"))

        entity_function = create_agent_entity(mock_agent)

        mock_context = Mock()
        mock_context.operation_name = "run_agent"
        mock_context.get_input.return_value = {
            "message": "Test message",
            "thread_id": "conv-789",
            "role": "user",
            "enable_tool_calls": True,
            "correlationId": "corr-runreq-6",
        }
        mock_context.get_state.return_value = None

        await asyncio.to_thread(entity_function, mock_context)

        # Verify result was set
        assert mock_context.set_result.called
        result = mock_context.set_result.call_args[0][0]
        assert isinstance(result, dict)

        # Check if messages are present
        assert "messages" in result
        assert len(result["messages"]) > 0
        message = result["messages"][0]

        # Check for text in various possible locations
        text_found = False
        if "text" in message and message["text"] == "Response":
            text_found = True
        elif "contents" in message:
            for content in message["contents"]:
                if isinstance(content, dict) and content.get("text") == "Response":
                    text_found = True
                    break

        assert text_found, f"Response text not found in message: {message}"


class TestDurableAgentStateRequestOrchestrationId:
    """Test suite for DurableAgentStateRequest orchestration_id field."""

    def test_request_with_orchestration_id(self) -> None:
        """Test creating a request with an orchestration_id."""
        request = DurableAgentStateRequest(
            correlation_id="corr-123",
            created_at=datetime.now(),
            messages=[
                DurableAgentStateMessage(
                    role="user",
                    contents=[DurableAgentStateTextContent(text="test")],
                )
            ],
            orchestration_id="orch-456",
        )

        assert request.orchestration_id == "orch-456"

    def test_request_to_dict_includes_orchestration_id(self) -> None:
        """Test that to_dict includes orchestrationId when set."""
        request = DurableAgentStateRequest(
            correlation_id="corr-123",
            created_at=datetime.now(),
            messages=[
                DurableAgentStateMessage(
                    role="user",
                    contents=[DurableAgentStateTextContent(text="test")],
                )
            ],
            orchestration_id="orch-789",
        )

        data = request.to_dict()

        assert "orchestrationId" in data
        assert data["orchestrationId"] == "orch-789"

    def test_request_to_dict_excludes_orchestration_id_when_none(self) -> None:
        """Test that to_dict excludes orchestrationId when not set."""
        request = DurableAgentStateRequest(
            correlation_id="corr-123",
            created_at=datetime.now(),
            messages=[
                DurableAgentStateMessage(
                    role="user",
                    contents=[DurableAgentStateTextContent(text="test")],
                )
            ],
        )

        data = request.to_dict()

        assert "orchestrationId" not in data

    def test_request_from_dict_with_orchestration_id(self) -> None:
        """Test from_dict correctly parses orchestrationId."""
        data = {
            "$type": "request",
            "correlationId": "corr-123",
            "createdAt": "2024-01-01T00:00:00Z",
            "messages": [{"role": "user", "contents": [{"$type": "text", "text": "test"}]}],
            "orchestrationId": "orch-from-dict",
        }

        request = DurableAgentStateRequest.from_dict(data)

        assert request.orchestration_id == "orch-from-dict"

    def test_request_from_run_request_with_orchestration_id(self) -> None:
        """Test from_run_request correctly transfers orchestration_id."""
        run_request = RunRequest(
            message="test message",
            correlation_id="corr-run",
            orchestration_id="orch-from-run-request",
        )

        durable_request = DurableAgentStateRequest.from_run_request(run_request)

        assert durable_request.orchestration_id == "orch-from-run-request"

    def test_request_from_run_request_without_orchestration_id(self) -> None:
        """Test from_run_request correctly handles missing orchestration_id."""
        run_request = RunRequest(
            message="test message",
            correlation_id="corr-run",
        )

        durable_request = DurableAgentStateRequest.from_run_request(run_request)

        assert durable_request.orchestration_id is None


class TestDurableAgentStateMessageCreatedAt:
    """Test suite for DurableAgentStateMessage created_at field handling."""

    def test_message_from_run_request_without_created_at_preserves_none(self) -> None:
        """Test from_run_request preserves None created_at instead of defaulting to current time.

        When a RunRequest has no created_at value, the resulting DurableAgentStateMessage
        should also have None for created_at, not default to current UTC time.
        """
        run_request = RunRequest(
            message="test message",
            correlation_id="corr-run",
            created_at=None,  # Explicitly None
        )

        durable_message = DurableAgentStateMessage.from_run_request(run_request)

        assert durable_message.created_at is None

    def test_message_from_run_request_with_created_at_parses_correctly(self) -> None:
        """Test from_run_request correctly parses a valid created_at timestamp."""
        run_request = RunRequest(
            message="test message",
            correlation_id="corr-run",
            created_at="2024-01-15T10:30:00Z",
        )

        durable_message = DurableAgentStateMessage.from_run_request(run_request)

        assert durable_message.created_at is not None
        assert durable_message.created_at.year == 2024
        assert durable_message.created_at.month == 1
        assert durable_message.created_at.day == 15


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
