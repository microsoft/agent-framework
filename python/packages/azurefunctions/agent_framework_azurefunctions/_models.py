# Copyright (c) Microsoft. All rights reserved.

"""Data models for Durable Agent Framework.

This module defines the request and response models used by the framework.
"""

from __future__ import annotations

import inspect
import uuid
from collections.abc import MutableMapping
from dataclasses import dataclass
from importlib import import_module
from typing import TYPE_CHECKING, Any, cast

import azure.durable_functions as df
from agent_framework import AgentThread, Role

if TYPE_CHECKING:  # pragma: no cover - type checking imports only
    from pydantic import BaseModel

_PydanticBaseModel: type[BaseModel] | None

try:
    from pydantic import BaseModel as _RuntimeBaseModel
except ImportError:  # pragma: no cover - optional dependency
    _PydanticBaseModel = None
else:
    _PydanticBaseModel = _RuntimeBaseModel


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


def _serialize_response_format(response_format: type[BaseModel] | None) -> Any:
    """Serialize response format for transport across durable function boundaries."""
    if response_format is None:
        return None

    if _PydanticBaseModel is None:
        raise RuntimeError("pydantic is required to use structured response formats")

    if not inspect.isclass(response_format) or not issubclass(response_format, _PydanticBaseModel):
        raise TypeError("response_format must be a Pydantic BaseModel type")

    return {
        "__response_schema_type__": "pydantic_model",
        "module": response_format.__module__,
        "qualname": response_format.__qualname__,
    }


def _deserialize_response_format(response_format: Any) -> type[BaseModel] | None:
    """Deserialize response format back into actionable type if possible."""
    if response_format is None:
        return None

    if (
        _PydanticBaseModel is not None
        and inspect.isclass(response_format)
        and issubclass(response_format, _PydanticBaseModel)
    ):
        return response_format

    if not isinstance(response_format, dict):
        return None

    response_dict = cast(dict[str, Any], response_format)

    if response_dict.get("__response_schema_type__") != "pydantic_model":
        return None

    module_name = response_dict.get("module")
    qualname = response_dict.get("qualname")
    if not module_name or not qualname:
        return None

    try:
        module = import_module(module_name)
    except ImportError:  # pragma: no cover - user provided module missing
        return None

    attr: Any = module
    for part in qualname.split("."):
        try:
            attr = getattr(attr, part)
        except AttributeError:  # pragma: no cover - invalid qualname
            return None

    if _PydanticBaseModel is not None and inspect.isclass(attr) and issubclass(attr, _PydanticBaseModel):
        return attr

    return None


@dataclass
class RunRequest:
    """Represents a request to run an agent with a specific message and configuration.

    Attributes:
        message: The message to send to the agent
        role: The role of the message sender (user, system, or assistant)
        response_format: Optional Pydantic BaseModel type describing the structured response format
        enable_tool_calls: Whether to enable tool calls for this request
        thread_id: Optional thread ID for tracking
        correlation_id: Optional correlation ID for tracking the response to this specific request
    """

    message: str
    role: Role = Role.USER
    response_format: type[BaseModel] | None = None
    enable_tool_calls: bool = True
    thread_id: str | None = None
    correlation_id: str | None = None

    def __init__(
        self,
        message: str,
        role: Role | str | None = Role.USER,
        response_format: type[BaseModel] | None = None,
        enable_tool_calls: bool = True,
        thread_id: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        self.message = message
        self.role = self.coerce_role(role)
        self.response_format = response_format
        self.enable_tool_calls = enable_tool_calls
        self.thread_id = thread_id
        self.correlation_id = correlation_id

    @staticmethod
    def coerce_role(value: Role | str | None) -> Role:
        """Normalize various role representations into a Role instance."""
        if isinstance(value, Role):
            return value
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                return Role.USER
            return Role(value=normalized.lower())
        return Role.USER

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "message": self.message,
            "enable_tool_calls": self.enable_tool_calls,
            "role": self.role.value,
        }
        if self.response_format:
            result["response_format"] = _serialize_response_format(self.response_format)
        if self.thread_id:
            result["thread_id"] = self.thread_id
        if self.correlation_id:
            result["correlation_id"] = self.correlation_id
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunRequest:
        """Create RunRequest from dictionary."""
        return cls(
            message=data.get("message", ""),
            role=cls.coerce_role(data.get("role")),
            response_format=_deserialize_response_format(data.get("response_format")),
            enable_tool_calls=data.get("enable_tool_calls", True),
            thread_id=data.get("thread_id"),
            correlation_id=data.get("correlation_id"),
        )


@dataclass
class AgentResponse:
    """Response from agent execution.

    Attributes:
        response: The agent's text response (or None for structured responses)
        message: The original message sent to the agent
        thread_id: The thread identifier
        status: Status of the execution (success, error, etc.)
        message_count: Number of messages in the conversation
        error: Error message if status is error
        error_type: Type of error if status is error
        structured_response: Structured response if response_format was provided
    """

    response: str | None
    message: str
    thread_id: str | None
    status: str
    message_count: int = 0
    error: str | None = None
    error_type: str | None = None
    structured_response: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result: dict[str, Any] = {
            "message": self.message,
            "thread_id": self.thread_id,
            "status": self.status,
            "message_count": self.message_count,
        }

        # Add response or structured_response based on what's available
        if self.structured_response is not None:
            result["structured_response"] = self.structured_response
        elif self.response is not None:
            result["response"] = self.response

        if self.error:
            result["error"] = self.error
        if self.error_type:
            result["error_type"] = self.error_type

        return result
