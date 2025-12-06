# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for HumanInputHookMixin and related classes."""

from agent_framework import (
    ChatMessage,
    HumanInputHookMixin,
    HumanInputRequest,
    Role,
)
from agent_framework._workflows._human_input import _HumanInputInterceptor  # type: ignore


class TestHumanInputRequest:
    """Tests for HumanInputRequest dataclass."""

    def test_create_request(self):
        """Test creating a HumanInputRequest with all fields."""
        conversation = [ChatMessage(role=Role.USER, text="Hello")]
        request = HumanInputRequest(
            prompt="Please review:",
            conversation=conversation,
            source_agent_id="test_agent",
            metadata={"key": "value"},
        )

        assert request.prompt == "Please review:"
        assert request.conversation == conversation
        assert request.source_agent_id == "test_agent"
        assert request.metadata == {"key": "value"}

    def test_create_request_defaults(self):
        """Test creating a HumanInputRequest with default values."""
        request = HumanInputRequest(prompt="Enter input:")

        assert request.prompt == "Enter input:"
        assert request.conversation == []
        assert request.source_agent_id is None
        assert request.metadata == {}


class TestHumanInputHookMixin:
    """Tests for HumanInputHookMixin."""

    def test_mixin_with_hook(self):
        """Test setting a human input hook via the mixin."""

        class TestBuilder(HumanInputHookMixin):
            pass

        def my_hook(
            conversation: list[ChatMessage],
            agent_id: str | None,
        ) -> HumanInputRequest | None:
            return None

        builder = TestBuilder()
        result = builder.with_human_input_hook(my_hook)

        assert result is builder  # Method chaining
        assert builder._human_input_hook is my_hook  # type: ignore

    def test_create_executor_returns_none_without_hook(self):
        """Test that _create_human_input_executor returns None when no hook is set."""

        class TestBuilder(HumanInputHookMixin):
            pass

        builder = TestBuilder()
        executor = builder._create_human_input_executor()  # type: ignore

        assert executor is None

    def test_create_executor_returns_interceptor_with_hook(self):
        """Test that _create_human_input_executor returns an interceptor when hook is set."""

        class TestBuilder(HumanInputHookMixin):
            pass

        def my_hook(
            conversation: list[ChatMessage],
            agent_id: str | None,
        ) -> HumanInputRequest | None:
            return None

        builder = TestBuilder()
        builder.with_human_input_hook(my_hook)
        executor = builder._create_human_input_executor("custom_id")  # type: ignore

        assert executor is not None
        assert isinstance(executor, _HumanInputInterceptor)
        assert executor.id == "custom_id"


class TestHumanInputInterceptor:
    """Tests for _HumanInputInterceptor executor."""

    async def test_invoke_sync_hook(self):
        """Test invoking a synchronous hook."""

        def sync_hook(
            conversation: list[ChatMessage],
            agent_id: str | None,
        ) -> HumanInputRequest | None:
            if conversation and "review" in conversation[-1].text.lower():
                return HumanInputRequest(
                    prompt="Review requested",
                    conversation=conversation,
                    source_agent_id=agent_id,
                )
            return None

        interceptor = _HumanInputInterceptor(sync_hook)

        # Test hook returns None
        result = await interceptor._invoke_hook([], None)  # type: ignore
        assert result is None

        # Test hook returns request
        conversation = [ChatMessage(role=Role.ASSISTANT, text="Please review this")]
        result = await interceptor._invoke_hook(conversation, "test_agent")  # type: ignore
        assert result is not None
        assert result.prompt == "Review requested"
        assert result.source_agent_id == "test_agent"

    async def test_invoke_async_hook(self):
        """Test invoking an asynchronous hook."""

        async def async_hook(
            conversation: list[ChatMessage],
            agent_id: str | None,
        ) -> HumanInputRequest | None:
            if conversation:
                return HumanInputRequest(
                    prompt="Async review",
                    conversation=conversation,
                    source_agent_id=agent_id,
                )
            return None

        interceptor = _HumanInputInterceptor(async_hook)

        # Test async hook returns request
        conversation = [ChatMessage(role=Role.USER, text="Test")]
        result = await interceptor._invoke_hook(conversation, "async_agent")  # type: ignore
        assert result is not None
        assert result.prompt == "Async review"
