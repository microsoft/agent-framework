# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for orchestration request info support."""

from collections.abc import AsyncIterable
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_framework import (
    AgentProtocol,
    AgentResponse,
    AgentResponseUpdate,
    AgentThread,
    ChatMessage,
    Role,
)
from agent_framework._workflows._agent_executor import AgentExecutorRequest, AgentExecutorResponse
from agent_framework._workflows._orchestration_request_info import (
    AgentApprovalExecutor,
    AgentRequestInfoExecutor,
    AgentRequestInfoResponse,
    resolve_request_info_filter,
)
from agent_framework._workflows._workflow_context import WorkflowContext


class TestResolveRequestInfoFilter:
    """Tests for resolve_request_info_filter function."""

    def test_returns_empty_set_for_none_input(self):
        """Test that None input returns empty set (no filtering)."""
        result = resolve_request_info_filter(None)
        assert result == set()

    def test_returns_empty_set_for_empty_list(self):
        """Test that empty list returns empty set."""
        result = resolve_request_info_filter([])
        assert result == set()

    def test_resolves_string_names(self):
        """Test resolving string agent names."""
        result = resolve_request_info_filter(["agent1", "agent2"])
        assert result == {"agent1", "agent2"}

    def test_resolves_agent_display_names(self):
        """Test resolving AgentProtocol instances by name attribute."""
        agent1 = MagicMock(spec=AgentProtocol)
        agent1.name = "writer"
        agent2 = MagicMock(spec=AgentProtocol)
        agent2.name = "reviewer"

        result = resolve_request_info_filter([agent1, agent2])
        assert result == {"writer", "reviewer"}

    def test_mixed_types(self):
        """Test resolving a mix of strings and agents."""
        agent = MagicMock(spec=AgentProtocol)
        agent.name = "writer"

        result = resolve_request_info_filter(["manual_name", agent])
        assert result == {"manual_name", "writer"}

    def test_raises_on_unsupported_type(self):
        """Test that unsupported types raise TypeError."""
        with pytest.raises(TypeError, match="Unsupported type for request_info filter"):
            resolve_request_info_filter([123])  # type: ignore


class TestAgentRequestInfoResponse:
    """Tests for AgentRequestInfoResponse dataclass."""

    def test_create_response_with_messages(self):
        """Test creating an AgentRequestInfoResponse with messages."""
        messages = [ChatMessage(role=Role.USER, text="Additional info")]
        response = AgentRequestInfoResponse(messages=messages)

        assert response.messages == messages

    def test_from_messages_factory(self):
        """Test creating response from ChatMessage list."""
        messages = [
            ChatMessage(role=Role.USER, text="Message 1"),
            ChatMessage(role=Role.USER, text="Message 2"),
        ]
        response = AgentRequestInfoResponse.from_messages(messages)

        assert response.messages == messages

    def test_from_strings_factory(self):
        """Test creating response from string list."""
        texts = ["First message", "Second message"]
        response = AgentRequestInfoResponse.from_strings(texts)

        assert len(response.messages) == 2
        assert response.messages[0].role == Role.USER
        assert response.messages[0].text == "First message"
        assert response.messages[1].role == Role.USER
        assert response.messages[1].text == "Second message"

    def test_approve_factory(self):
        """Test creating an approval response (empty messages)."""
        response = AgentRequestInfoResponse.approve()

        assert response.messages == []


class TestAgentRequestInfoExecutor:
    """Tests for AgentRequestInfoExecutor."""

    @pytest.mark.asyncio
    async def test_request_info_handler(self):
        """Test that request_info handler calls ctx.request_info."""
        executor = AgentRequestInfoExecutor(id="test_executor")

        agent_response = AgentResponse(messages=[ChatMessage(role=Role.ASSISTANT, text="Agent response")])
        agent_response = AgentExecutorResponse(
            executor_id="test_agent",
            agent_response=agent_response,
        )

        ctx = MagicMock(spec=WorkflowContext)
        ctx.request_info = AsyncMock()

        await executor.request_info(agent_response, ctx)

        ctx.request_info.assert_called_once_with(agent_response, AgentRequestInfoResponse)

    @pytest.mark.asyncio
    async def test_handle_request_info_response_with_messages(self):
        """Test response handler when user provides additional messages."""
        executor = AgentRequestInfoExecutor(id="test_executor")

        agent_response = AgentResponse(messages=[ChatMessage(role=Role.ASSISTANT, text="Original")])
        original_request = AgentExecutorResponse(
            executor_id="test_agent",
            agent_response=agent_response,
        )

        response = AgentRequestInfoResponse.from_strings(["Additional input"])

        ctx = MagicMock(spec=WorkflowContext)
        ctx.send_message = AsyncMock()

        await executor.handle_request_info_response(original_request, response, ctx)

        # Should send new request with additional messages
        ctx.send_message.assert_called_once()
        call_args = ctx.send_message.call_args[0][0]
        assert isinstance(call_args, AgentExecutorRequest)
        assert call_args.should_respond is True
        assert len(call_args.messages) == 1
        assert call_args.messages[0].text == "Additional input"

    @pytest.mark.asyncio
    async def test_handle_request_info_response_approval(self):
        """Test response handler when user approves (no additional messages)."""
        executor = AgentRequestInfoExecutor(id="test_executor")

        agent_response = AgentResponse(messages=[ChatMessage(role=Role.ASSISTANT, text="Original")])
        original_request = AgentExecutorResponse(
            executor_id="test_agent",
            agent_response=agent_response,
        )

        response = AgentRequestInfoResponse.approve()

        ctx = MagicMock(spec=WorkflowContext)
        ctx.yield_output = AsyncMock()

        await executor.handle_request_info_response(original_request, response, ctx)

        # Should yield original response without modification
        ctx.yield_output.assert_called_once_with(original_request)


class _TestAgent:
    """Simple test agent implementation."""

    def __init__(self, id: str, name: str | None = None, description: str | None = None):
        self._id = id
        self._name = name
        self._description = description

    @property
    def id(self) -> str:
        return self._id

    @property
    def name(self) -> str | None:
        return self._name

    @property
    def display_name(self) -> str:
        return self._name or self._id

    @property
    def description(self) -> str | None:
        return self._description

    async def run(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AgentResponse:
        """Dummy run method."""
        return AgentResponse(messages=[ChatMessage(role=Role.ASSISTANT, text="Test response")])

    def run_stream(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[AgentResponseUpdate]:
        """Dummy run_stream method."""

        async def generator():
            yield AgentResponseUpdate(messages=[ChatMessage(role=Role.ASSISTANT, text="Test response stream")])

        return generator()

    def get_new_thread(self, **kwargs: Any) -> AgentThread:
        """Creates a new conversation thread for the agent."""
        return AgentThread(**kwargs)


class TestAgentApprovalExecutor:
    """Tests for AgentApprovalExecutor."""

    def test_initialization(self):
        """Test that AgentApprovalExecutor initializes correctly."""
        agent = _TestAgent(id="test_id", name="test_agent", description="Test agent description")

        executor = AgentApprovalExecutor(agent)

        assert executor.id == "test_agent"
        assert executor.description == "Test agent description"

    def test_builds_workflow_with_agent_and_request_info_executors(self):
        """Test that the internal workflow is created successfully."""
        agent = _TestAgent(id="test_id", name="test_agent", description="Test description")

        executor = AgentApprovalExecutor(agent)

        # Verify the executor has a workflow
        assert executor.workflow is not None
        assert executor.id == "test_agent"

    def test_propagate_request_enabled(self):
        """Test that AgentApprovalExecutor has propagate_request enabled."""
        agent = _TestAgent(id="test_id", name="test_agent", description="Test description")

        executor = AgentApprovalExecutor(agent)

        assert executor._propagate_request is True  # type: ignore
