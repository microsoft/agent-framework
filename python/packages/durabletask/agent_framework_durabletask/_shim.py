# Copyright (c) Microsoft. All rights reserved.

"""Durable Agent Shim for Durable Task Framework.

This module provides the DurableAIAgent shim that implements AgentProtocol
and provides a consistent interface for both Client and Orchestration contexts.
The actual execution is delegated to the context-specific providers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any, Generic, TypeVar

from agent_framework import AgentProtocol, AgentRunResponseUpdate, AgentThread, ChatMessage
from pydantic import BaseModel

from ._executors import DurableAgentExecutor
from ._models import DurableAgentThread

# TypeVar for the task type returned by executors
# Covariant because TaskT only appears in return positions (output)
TaskT = TypeVar("TaskT", covariant=True)


class DurableAgentProvider(ABC, Generic[TaskT]):
    """Abstract provider for constructing durable agent proxies.

    Implemented by context-specific wrappers (client/orchestration) to return a
    `DurableAIAgent` shim backed by their respective `DurableAgentExecutor`
    implementation, ensuring a consistent `get_agent` entry point regardless of
    execution context.
    """

    @abstractmethod
    def get_agent(self, agent_name: str) -> DurableAIAgent[TaskT]:
        """Retrieve a DurableAIAgent shim for the specified agent.

        Args:
            agent_name: Name of the agent to retrieve

        Returns:
            DurableAIAgent instance that can be used to run the agent

        Raises:
            NotImplementedError: Must be implemented by subclasses
        """
        raise NotImplementedError("Subclasses must implement get_agent()")


class DurableAIAgent(AgentProtocol, Generic[TaskT]):
    """A durable agent proxy that delegates execution to the provider.

    This class implements AgentProtocol but with one critical difference:
    - AgentProtocol.run() returns a Coroutine (async, must await)
    - DurableAIAgent.run() returns TaskT (sync Task object, must yield)

    This represents fundamentally different execution models but maintains the same
    interface contract for all other properties and methods.

    The underlying provider determines how execution occurs (entity calls, HTTP requests, etc.)
    and what type of Task object is returned.

    Type Parameters:
        TaskT: The task type returned by this agent (e.g., DurableAgentTask, AgentTask)

    Note:
        This class intentionally does NOT inherit from BaseAgent because:
        - BaseAgent assumes async/await patterns
        - Orchestration contexts require yield patterns
        - BaseAgent methods like as_tool() would fail in orchestrations
    """

    def __init__(self, executor: DurableAgentExecutor[TaskT], name: str, *, agent_id: str | None = None):
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

    def run(  # pyright: ignore[reportIncompatibleMethodOverride]
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        response_format: type[BaseModel] | None = None,
        enable_tool_calls: bool = True,
    ) -> TaskT:
        """Execute the agent via the injected provider.

        Note:
            This method overrides AgentProtocol.run() with a different return type:
            - AgentProtocol.run() returns Coroutine[Any, Any, AgentRunResponse] (async)
            - DurableAIAgent.run() returns TaskT (Task object for yielding)

            This is intentional to support orchestration contexts that use yield patterns
            instead of async/await patterns.

        Returns:
            TaskT: The task type specific to the executor (e.g., DurableAgentTask or AgentTask)
        """
        message_str = self._normalize_messages(messages)

        run_request = self._executor.get_run_request(
            message=message_str,
            response_format=response_format,
            enable_tool_calls=enable_tool_calls,
        )

        return self._executor.run_durable_agent(
            agent_name=self._name,
            run_request=run_request,
            thread=thread,
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

    def get_new_thread(self, **kwargs: Any) -> DurableAgentThread:
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
