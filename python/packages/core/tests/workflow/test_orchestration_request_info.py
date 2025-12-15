# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for request info support in high-level builders."""

from typing import Any
from unittest.mock import MagicMock

from agent_framework import (
    AgentInputRequest,
    AgentProtocol,
    AgentResponseReviewRequest,
    ChatMessage,
    RequestInfoInterceptor,
    Role,
)
from agent_framework._workflows._executor import Executor, handler
from agent_framework._workflows._orchestration_request_info import resolve_request_info_filter
from agent_framework._workflows._workflow_context import WorkflowContext


class DummyExecutor(Executor):
    """Dummy executor with a handler for testing."""

    @handler
    async def handle(self, data: str, ctx: WorkflowContext[Any, Any]) -> None:
        pass


class TestResolveRequestInfoFilter:
    """Tests for resolve_request_info_filter function."""

    def test_returns_none_for_none_input(self):
        """Test that None input returns None (no filtering)."""
        result = resolve_request_info_filter(None)
        assert result is None

    def test_returns_none_for_empty_list(self):
        """Test that empty list returns None."""
        result = resolve_request_info_filter([])
        assert result is None

    def test_resolves_string_names(self):
        """Test resolving string agent names."""
        result = resolve_request_info_filter(["agent1", "agent2"])
        assert result == {"agent1", "agent2"}

    def test_resolves_executor_ids(self):
        """Test resolving Executor instances by ID."""
        exec1 = DummyExecutor(id="executor1")
        exec2 = DummyExecutor(id="executor2")

        result = resolve_request_info_filter([exec1, exec2])
        assert result == {"executor1", "executor2"}

    def test_resolves_agent_names(self):
        """Test resolving AgentProtocol-like objects by name attribute."""
        agent1 = MagicMock(spec=AgentProtocol)
        agent1.name = "writer"
        agent2 = MagicMock(spec=AgentProtocol)
        agent2.name = "reviewer"

        result = resolve_request_info_filter([agent1, agent2])
        assert result == {"writer", "reviewer"}

    def test_mixed_types(self):
        """Test resolving a mix of strings, agents, and executors."""
        agent = MagicMock(spec=AgentProtocol)
        agent.name = "writer"
        executor = DummyExecutor(id="custom_exec")

        result = resolve_request_info_filter(["manual_name", agent, executor])
        assert result == {"manual_name", "writer", "custom_exec"}

    def test_skips_agent_without_name(self):
        """Test that agents without names are skipped."""
        agent_with_name = MagicMock(spec=AgentProtocol)
        agent_with_name.name = "valid"
        agent_without_name = MagicMock(spec=AgentProtocol)
        agent_without_name.name = None

        result = resolve_request_info_filter([agent_with_name, agent_without_name])
        assert result == {"valid"}


class TestAgentInputRequest:
    """Tests for AgentInputRequest dataclass (formerly AgentResponseReviewRequest)."""

    def test_create_request(self):
        """Test creating an AgentInputRequest with all fields."""
        conversation = [ChatMessage(role=Role.USER, text="Hello")]
        request = AgentInputRequest(
            target_agent_id="test_agent",
            conversation=conversation,
            instruction="Review this",
            metadata={"key": "value"},
        )

        assert request.target_agent_id == "test_agent"
        assert request.conversation == conversation
        assert request.instruction == "Review this"
        assert request.metadata == {"key": "value"}

    def test_create_request_defaults(self):
        """Test creating an AgentInputRequest with default values."""
        request = AgentInputRequest(target_agent_id="test_agent")

        assert request.target_agent_id == "test_agent"
        assert request.conversation == []
        assert request.instruction is None
        assert request.metadata == {}

    def test_backward_compatibility_alias(self):
        """Test that AgentResponseReviewRequest is an alias for AgentInputRequest."""
        assert AgentResponseReviewRequest is AgentInputRequest


class TestRequestInfoInterceptor:
    """Tests for RequestInfoInterceptor executor."""

    def test_interceptor_creation_generates_unique_id(self):
        """Test creating a RequestInfoInterceptor generates unique IDs."""
        interceptor1 = RequestInfoInterceptor()
        interceptor2 = RequestInfoInterceptor()
        assert interceptor1.id.startswith("request_info_interceptor-")
        assert interceptor2.id.startswith("request_info_interceptor-")
        assert interceptor1.id != interceptor2.id

    def test_interceptor_with_custom_id(self):
        """Test creating a RequestInfoInterceptor with custom ID."""
        interceptor = RequestInfoInterceptor(executor_id="custom_review")
        assert interceptor.id == "custom_review"

    def test_interceptor_with_agent_filter(self):
        """Test creating a RequestInfoInterceptor with agent filter."""
        agent_filter = {"agent1", "agent2"}
        interceptor = RequestInfoInterceptor(
            executor_id="filtered_review",
            agent_filter=agent_filter,
        )
        assert interceptor.id == "filtered_review"
        assert interceptor._agent_filter == agent_filter

    def test_should_pause_for_agent_no_filter(self):
        """Test that interceptor pauses for all agents when no filter is set."""
        interceptor = RequestInfoInterceptor()
        assert interceptor._should_pause_for_agent("any_agent") is True
        assert interceptor._should_pause_for_agent("another_agent") is True
        assert interceptor._should_pause_for_agent(None) is True

    def test_should_pause_for_agent_with_filter(self):
        """Test that interceptor only pauses for agents in the filter."""
        agent_filter = {"writer", "reviewer"}
        interceptor = RequestInfoInterceptor(agent_filter=agent_filter)

        assert interceptor._should_pause_for_agent("writer") is True
        assert interceptor._should_pause_for_agent("reviewer") is True
        assert interceptor._should_pause_for_agent("drafter") is False
        assert interceptor._should_pause_for_agent(None) is False

    def test_should_pause_for_agent_with_prefixed_id(self):
        """Test that filter matches agent names in prefixed executor IDs."""
        agent_filter = {"writer"}
        interceptor = RequestInfoInterceptor(agent_filter=agent_filter)

        # Should match the name portion after the colon
        assert interceptor._should_pause_for_agent("groupchat_agent:writer") is True
        assert interceptor._should_pause_for_agent("request_info:writer") is True
        assert interceptor._should_pause_for_agent("groupchat_agent:editor") is False
