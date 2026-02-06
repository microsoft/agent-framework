# Copyright (c) Microsoft. All rights reserved.

"""Tests for agent run context propagation.

These tests verify that:
1. Agent run context is properly set during agent execution
2. Sub-agents can access parent context via get_current_agent_run_context()
3. Context is isolated between concurrent agent runs
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from unittest.mock import AsyncMock

from agent_framework import (
    AgentContext,
    ChatAgent,
    ChatMessage,
    ChatResponse,
    agent_middleware,
    get_current_agent_run_context,
)
from agent_framework._agent_context import agent_run_scope

from .conftest import MockChatClient


class TestAgentContext:
    """Tests for ambient agent run context."""

    async def test_context_not_available_outside_run(self) -> None:
        """Test that context is None outside of agent run."""
        context = get_current_agent_run_context()
        assert context is None

    async def test_context_scope_properly_restored(self) -> None:
        """Test that context is properly restored after scope exits."""
        mock_agent = AsyncMock()
        mock_agent.name = "test"

        mock_context = AgentContext(
            agent=mock_agent,
            messages=[],
            thread=None,
            options=None,
            stream=False,
            kwargs={},
        )

        # Before scope
        assert get_current_agent_run_context() is None

        # Inside scope
        with agent_run_scope(mock_context):
            assert get_current_agent_run_context() is mock_context

        # After scope
        assert get_current_agent_run_context() is None

    async def test_nested_context_scopes(self) -> None:
        """Test that nested context scopes work correctly."""
        mock_agent1 = AsyncMock()
        mock_agent1.name = "agent1"
        mock_agent2 = AsyncMock()
        mock_agent2.name = "agent2"

        context1 = AgentContext(agent=mock_agent1, messages=[], thread=None, options=None, stream=False, kwargs={})
        context2 = AgentContext(agent=mock_agent2, messages=[], thread=None, options=None, stream=False, kwargs={})

        with agent_run_scope(context1):
            assert get_current_agent_run_context() is context1

            with agent_run_scope(context2):
                assert get_current_agent_run_context() is context2

            # After inner scope exits, should restore outer context
            assert get_current_agent_run_context() is context1

        assert get_current_agent_run_context() is None

    async def test_context_isolated_between_concurrent_tasks(self) -> None:
        """Test that context is isolated between concurrent async tasks."""
        results: dict[str, AgentContext | None] = {}
        mock_agent1 = AsyncMock()
        mock_agent1.name = "agent1"
        mock_agent2 = AsyncMock()
        mock_agent2.name = "agent2"

        context1 = AgentContext(agent=mock_agent1, messages=[], thread=None, options=None, stream=False, kwargs={})
        context2 = AgentContext(agent=mock_agent2, messages=[], thread=None, options=None, stream=False, kwargs={})

        async def task1() -> None:
            with agent_run_scope(context1):
                await asyncio.sleep(0.01)  # Yield to other task
                results["task1"] = get_current_agent_run_context()

        async def task2() -> None:
            with agent_run_scope(context2):
                await asyncio.sleep(0.01)  # Yield to other task
                results["task2"] = get_current_agent_run_context()

        await asyncio.gather(task1(), task2())

        # Each task should see its own context
        assert results["task1"] is context1
        assert results["task2"] is context2

    async def test_context_available_in_middleware(self, chat_client: MockChatClient) -> None:
        """Test that agent run context is available in agent middleware."""
        captured_context: AgentContext | None = None

        @agent_middleware
        async def capture_middleware(
            context: AgentContext, next_handler: Callable[[AgentContext], Awaitable[None]]
        ) -> None:
            nonlocal captured_context
            # Get ambient context - should be the same as the passed context
            captured_context = get_current_agent_run_context()
            await next_handler(context)

        chat_client.responses = [
            ChatResponse(messages=[ChatMessage("assistant", ["Response"])]),
        ]

        agent = ChatAgent(chat_client=chat_client, name="test_agent", middleware=[capture_middleware])
        await agent.run("Test message")

        assert captured_context is not None
        assert captured_context.agent is agent
