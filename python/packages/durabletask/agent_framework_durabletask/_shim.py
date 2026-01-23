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

from agent_framework import AgentProtocol, AgentResponseUpdate, AgentThread, ChatMessage

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
    - DurableAIAgent.run() returns TaskT (sync Task object - must yield
        or the AgentResponse directly in the case of TaskHubGrpcClient)

    This represents fundamentally different execution models but maintains the same
    interface contract for all other properties and methods.

    The underlying provider determines how execution occurs (entity calls, HTTP requests, etc.)
    and what type of Task object is returned.

    Type Parameters:
        TaskT: The task type returned by this agent (e.g., AgentResponse, DurableAgentTask, AgentTask)
    """

    id: str
    name: str
    display_name: str
    description: str | None

    def __init__(self, executor: DurableAgentExecutor[TaskT], name: str, *, agent_id: str | None = None):
        """Initialize the shim with a provider and agent name.

        Args:
            executor: The execution provider (Client or OrchestrationContext)
            name: The name of the agent to execute
            agent_id: Optional unique identifier for the agent (defaults to name)
        """
        self._executor = executor
        self.name = name  # pyright: ignore[reportIncompatibleVariableOverride]
        self.id = agent_id if agent_id is not None else name
        self.display_name = name
        self.description = f"Durable agent proxy for {name}"

    def run(  # type: ignore[override]
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        options: dict[str, Any] | None = None,
    ) -> TaskT:
        """Execute the agent via the injected provider.

        Args:
            messages: The message(s) to send to the agent
            thread: Optional agent thread for conversation context
            options: Optional options dictionary. Supported keys include
                ``response_format``, ``enable_tool_calls``, and ``wait_for_response``.
                Additional keys are forwarded to the agent execution.

        Note:
            This method overrides AgentProtocol.run() with a different return type:
            - AgentProtocol.run() returns Coroutine[Any, Any, AgentResponse] (async)
            - DurableAIAgent.run() returns TaskT (Task object for yielding)

            This is intentional to support orchestration contexts that use yield patterns
            instead of async/await patterns.

        Returns:
            TaskT: The task type specific to the executor

        Raises:
            ValueError: If wait_for_response=False is used in an unsupported context
        """
        message_str = self._normalize_messages(messages)

        run_request = self._executor.get_run_request(
            message=message_str,
            options=options,
        )

        return self._executor.run_durable_agent(
            agent_name=self.name,
            run_request=run_request,
            thread=thread,
        )

    def run_stream(  # type: ignore[override]
        self,
        messages: str | ChatMessage | list[str] | list[ChatMessage] | None = None,
        *,
        thread: AgentThread | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[AgentResponseUpdate]:
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
        return self._executor.get_new_thread(self.name, **kwargs)

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
