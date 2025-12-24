# Copyright (c) Microsoft. All rights reserved.

"""Durable Agent Shim for Durable Task Framework.

This module provides the DurableAIAgent shim that implements AgentProtocol
and provides a consistent interface for both Client and Orchestration contexts.
The actual execution is delegated to the context-specific providers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from agent_framework import AgentProtocol, AgentRunResponseUpdate, AgentThread, ChatMessage
from pydantic import BaseModel

if TYPE_CHECKING:
    from ._executors import DurableAgentExecutor


class DurableAgentProvider(ABC):
    """Abstract provider for constructing durable agent proxies.

    Implemented by context-specific wrappers (client/orchestration) to return a
    `DurableAIAgent` shim backed by their respective `DurableAgentExecutor`
    implementation, ensuring a consistent `get_agent` entry point regardless of
    execution context.
    """

    @abstractmethod
    def get_agent(self, agent_name: str) -> DurableAIAgent:
        """Retrieve a DurableAIAgent shim for the specified agent.

        Args:
            agent_name: Name of the agent to retrieve

        Returns:
            DurableAIAgent instance that can be used to run the agent

        Raises:
            NotImplementedError: Must be implemented by subclasses
        """
        raise NotImplementedError("Subclasses must implement get_agent()")


class DurableAIAgent(AgentProtocol):
    """A durable agent proxy that delegates execution to the provider.

    This class implements AgentProtocol but doesn't contain any agent logic itself.
    Instead, it serves as a consistent interface that delegates to the underlying
    provider, which can be either:
    - DurableAIAgentClient (for external usage via HTTP/gRPC)
    - DurableAIAgentOrchestrationContext (for use inside orchestrations)

    The provider determines how execution occurs (entity calls, HTTP requests, etc.)
    and what type of Task object is returned (asyncio.Task vs durabletask.Task).

    Note:
        This class intentionally does NOT inherit from BaseAgent because:
        - BaseAgent assumes async/await patterns
        - Orchestration contexts require yield patterns
        - BaseAgent methods like as_tool() would fail in orchestrations
    """

    def __init__(self, executor: DurableAgentExecutor, name: str, *, agent_id: str | None = None):
        """Initialize the shim with a provider and agent name.

        Args:
            executor: The execution provider (Client or OrchestrationContext)
            name: The name of the agent to execute
            agent_id: Optional unique identifier for the agent (defaults to name)
        """
        self._executor = executor
        self._name = name
        self._id = agent_id if agent_id is not None else name
        self._display_name = name
        self._description = f"Durable agent proxy for {name}"

    @property
    def id(self) -> str:
        """Get the unique identifier for this agent."""
        return self._id

    @property
    def name(self) -> str | None:
        """Get the name of the agent."""
        return self._name

    @property
    def display_name(self) -> str:
        """Get the display name of the agent."""
        return self._display_name

    @property
    def description(self) -> str | None:
        """Get the description of the agent."""
        return self._description

    def run(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        response_format: type[BaseModel] | None = None,
        **kwargs: Any,
    ) -> Any:
        """Execute the agent via the injected provider.

        The provider determines whether the return is awaitable (client) or yieldable (orchestration).
        """
        message_str = self._normalize_messages(messages)
        return self._executor.run_durable_agent(
            agent_name=self._name,
            message=message_str,
            thread=thread,
            response_format=response_format,
            **kwargs,
        )

    def run_stream(
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[AgentRunResponseUpdate]:
        """Run the agent with streaming (not supported for durable agents).

        Args:
            messages: The message(s) to send to the agent
            thread: Optional agent thread for conversation context
            **kwargs: Additional arguments

        Raises:
            NotImplementedError: Streaming is not supported for durable agents
        """
        raise NotImplementedError("Streaming is not supported for durable agents")

    def get_new_thread(self, **kwargs: Any) -> AgentThread:
        """Create a new agent thread via the provider."""
        return self._executor.get_new_thread(self._name, **kwargs)

    def _normalize_messages(self, messages: str | ChatMessage | list[str] | list[ChatMessage] | None) -> str:
        """Convert supported message inputs to a single string.

        Args:
            messages: The messages to normalize

        Returns:
            A single string representation of the messages
        """
        if messages is None:
            return ""
        if isinstance(messages, str):
            return messages
        if isinstance(messages, ChatMessage):
            return messages.text or ""
        if isinstance(messages, list):
            if not messages:
                return ""
            first_item = messages[0]
            if isinstance(first_item, str):
                return "\n".join(messages)  # type: ignore[arg-type]
            # List of ChatMessage
            return "\n".join([msg.text or "" for msg in messages])  # type: ignore[union-attr]
        return ""
