# Copyright (c) Microsoft. All rights reserved.

"""Azure Functions-specific data models for Durable Agent Framework.

This module contains Azure Functions-specific models:
- AgentSessionId: Entity ID management for Azure Durable Entities
- DurableAgentThread: Thread implementation that tracks AgentSessionId

Common models like RunRequest have been moved to agent-framework-durabletask.
"""

from __future__ import annotations

import uuid
from collections.abc import MutableMapping
from dataclasses import dataclass
from typing import Any

import azure.durable_functions as df
from agent_framework import AgentThread


@dataclass
class AgentSessionId:
    """Represents an agent session ID, which is used to identify a long-running agent session.

    Attributes:
        name: The name of the agent that owns the session (case-insensitive)
        key: The unique key of the agent session (case-sensitive)
    """

    name: str
    key: str

    ENTITY_NAME_PREFIX: str = "dafx-"

    @staticmethod
    def to_entity_name(name: str) -> str:
        """Converts an agent name to an entity name by adding the DAFx prefix.

        Args:
            name: The agent name

        Returns:
            The entity name with the dafx- prefix
        """
        return f"{AgentSessionId.ENTITY_NAME_PREFIX}{name}"

    @staticmethod
    def with_random_key(name: str) -> AgentSessionId:
        """Creates a new AgentSessionId with the specified name and a randomly generated key.

        Args:
            name: The name of the agent that owns the session

        Returns:
            A new AgentSessionId with the specified name and a random GUID key
        """
        return AgentSessionId(name=name, key=uuid.uuid4().hex)

    def to_entity_id(self) -> df.EntityId:
        """Converts this AgentSessionId to a Durable Functions EntityId.

        Returns:
            EntityId for use with Durable Functions APIs
        """
        return df.EntityId(self.to_entity_name(self.name), self.key)

    @staticmethod
    def from_entity_id(entity_id: df.EntityId) -> AgentSessionId:
        """Creates an AgentSessionId from a Durable Functions EntityId.

        Args:
            entity_id: The EntityId to convert

        Returns:
            AgentSessionId instance

        Raises:
            ValueError: If the entity ID does not have the expected prefix
        """
        if not entity_id.name.startswith(AgentSessionId.ENTITY_NAME_PREFIX):
            raise ValueError(
                f"'{entity_id}' is not a valid agent session ID. "
                f"Expected entity name to start with '{AgentSessionId.ENTITY_NAME_PREFIX}'"
            )

        agent_name = entity_id.name[len(AgentSessionId.ENTITY_NAME_PREFIX) :]
        return AgentSessionId(name=agent_name, key=entity_id.key)

    def __str__(self) -> str:
        """Returns a string representation in the form @name@key."""
        return f"@{self.name}@{self.key}"

    def __repr__(self) -> str:
        """Returns a detailed string representation."""
        return f"AgentSessionId(name='{self.name}', key='{self.key}')"

    @staticmethod
    def parse(session_id_string: str) -> AgentSessionId:
        """Parses a string representation of an agent session ID.

        Args:
            session_id_string: A string in the form @name@key

        Returns:
            AgentSessionId instance

        Raises:
            ValueError: If the string format is invalid
        """
        if not session_id_string.startswith("@"):
            raise ValueError(f"Invalid agent session ID format: {session_id_string}")

        parts = session_id_string[1:].split("@", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid agent session ID format: {session_id_string}")

        return AgentSessionId(name=parts[0], key=parts[1])


class DurableAgentThread(AgentThread):
    """Durable agent thread that tracks the owning :class:`AgentSessionId`."""

    _SERIALIZED_SESSION_ID_KEY = "durable_session_id"

    def __init__(
        self,
        *,
        session_id: AgentSessionId | None = None,
        service_thread_id: str | None = None,
        message_store: Any = None,
        context_provider: Any = None,
    ) -> None:
        super().__init__(
            service_thread_id=service_thread_id,
            message_store=message_store,
            context_provider=context_provider,
        )
        self._session_id: AgentSessionId | None = session_id

    @property
    def session_id(self) -> AgentSessionId | None:
        """Returns the durable agent session identifier for this thread."""
        return self._session_id

    def attach_session(self, session_id: AgentSessionId) -> None:
        """Associates the thread with the provided :class:`AgentSessionId`."""
        self._session_id = session_id

    @classmethod
    def from_session_id(
        cls,
        session_id: AgentSessionId,
        *,
        service_thread_id: str | None = None,
        message_store: Any = None,
        context_provider: Any = None,
    ) -> DurableAgentThread:
        """Creates a durable thread pre-associated with the supplied session ID."""
        return cls(
            session_id=session_id,
            service_thread_id=service_thread_id,
            message_store=message_store,
            context_provider=context_provider,
        )

    async def serialize(self, **kwargs: Any) -> dict[str, Any]:
        """Serializes thread state including the durable session identifier."""
        state = await super().serialize(**kwargs)
        if self._session_id is not None:
            state[self._SERIALIZED_SESSION_ID_KEY] = str(self._session_id)
        return state

    @classmethod
    async def deserialize(
        cls,
        serialized_thread_state: MutableMapping[str, Any],
        *,
        message_store: Any = None,
        **kwargs: Any,
    ) -> DurableAgentThread:
        """Restores a durable thread, rehydrating the stored session identifier."""
        state_payload = dict(serialized_thread_state)
        session_id_value = state_payload.pop(cls._SERIALIZED_SESSION_ID_KEY, None)
        thread = await super().deserialize(
            state_payload,
            message_store=message_store,
            **kwargs,
        )
        if not isinstance(thread, DurableAgentThread):
            raise TypeError("Deserialized thread is not a DurableAgentThread instance")

        if session_id_value is None:
            return thread

        if not isinstance(session_id_value, str):
            raise ValueError("durable_session_id must be a string when present in serialized state")

        thread.attach_session(AgentSessionId.parse(session_id_value))
        return thread
