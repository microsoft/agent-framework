# Copyright (c) Microsoft. All rights reserved.

"""Data models for Durable Agent Framework.

This module defines the request and response models used by the framework.
"""

from __future__ import annotations

import inspect
import json
import uuid
from collections.abc import MutableMapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from importlib import import_module
from typing import TYPE_CHECKING, Any, cast

from agent_framework import AgentThread, Role

from ._constants import REQUEST_RESPONSE_FORMAT_TEXT

if TYPE_CHECKING:  # pragma: no cover - type checking imports only
    from pydantic import BaseModel

_PydanticBaseModel: type[BaseModel] | None

try:
    from pydantic import BaseModel as _RuntimeBaseModel
except ImportError:  # pragma: no cover - optional dependency
    _PydanticBaseModel = None
else:
    _PydanticBaseModel = _RuntimeBaseModel


def serialize_response_format(response_format: type[BaseModel] | None) -> Any:
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
        request_response_format: The desired response format (e.g., "text" or "json")
        role: The role of the message sender (user, system, or assistant)
        response_format: Optional Pydantic BaseModel type describing the structured response format
        enable_tool_calls: Whether to enable tool calls for this request
        wait_for_response: If True (default), caller will wait for agent response. If False,
                          returns immediately after signaling (fire-and-forget mode)
        correlation_id: Correlation ID for tracking the response to this specific request
        created_at: Optional timestamp when the request was created
        orchestration_id: Optional ID of the orchestration that initiated this request
        options: Optional options dictionary forwarded to the agent
    """

    message: str
    request_response_format: str
    correlation_id: str
    role: Role = Role.USER
    response_format: type[BaseModel] | None = None
    enable_tool_calls: bool = True
    wait_for_response: bool = True
    created_at: datetime | None = None
    orchestration_id: str | None = None
    options: dict[str, Any] = field(default_factory=lambda: {})

    def __init__(
        self,
        message: str,
        correlation_id: str,
        request_response_format: str = REQUEST_RESPONSE_FORMAT_TEXT,
        role: Role | str | None = Role.USER,
        response_format: type[BaseModel] | None = None,
        enable_tool_calls: bool = True,
        wait_for_response: bool = True,
        created_at: datetime | None = None,
        orchestration_id: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> None:
        self.message = message
        self.correlation_id = correlation_id
        self.role = self.coerce_role(role)
        self.response_format = response_format
        self.request_response_format = request_response_format
        self.enable_tool_calls = enable_tool_calls
        self.wait_for_response = wait_for_response
        self.created_at = created_at if created_at is not None else datetime.now(tz=timezone.utc)
        self.orchestration_id = orchestration_id
        self.options = options if options is not None else {}

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
            "wait_for_response": self.wait_for_response,
            "role": self.role.value,
            "request_response_format": self.request_response_format,
            "correlationId": self.correlation_id,
            "options": self.options,
        }
        if self.response_format:
            result["response_format"] = serialize_response_format(self.response_format)
        if self.created_at:
            result["created_at"] = self.created_at.isoformat()
        if self.orchestration_id:
            result["orchestrationId"] = self.orchestration_id
        return result

    @classmethod
    def from_json(cls, data: str) -> RunRequest:
        """Create RunRequest from JSON string."""
        try:
            dict_data = json.loads(data)
        except json.JSONDecodeError as e:
            raise ValueError("The durable agent state is not valid JSON.") from e

        return cls.from_dict(dict_data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunRequest:
        """Create RunRequest from dictionary."""
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            try:
                created_at = datetime.fromisoformat(created_at)
            except ValueError:
                created_at = None

        correlation_id = data.get("correlationId")
        if not correlation_id:
            raise ValueError("correlationId is required in RunRequest data")

        options = data.get("options")

        return cls(
            message=data.get("message", ""),
            correlation_id=correlation_id,
            request_response_format=data.get("request_response_format", REQUEST_RESPONSE_FORMAT_TEXT),
            role=cls.coerce_role(data.get("role")),
            response_format=_deserialize_response_format(data.get("response_format")),
            wait_for_response=data.get("wait_for_response", True),
            enable_tool_calls=data.get("enable_tool_calls", True),
            created_at=created_at,
            orchestration_id=data.get("orchestrationId"),
            options=cast(dict[str, Any], options) if isinstance(options, dict) else {},
        )


@dataclass
class AgentSessionId:
    """Represents an agent session identifier (name + key)."""

    name: str
    key: str

    ENTITY_NAME_PREFIX: str = "dafx-"

    @staticmethod
    def to_entity_name(name: str) -> str:
        return f"{AgentSessionId.ENTITY_NAME_PREFIX}{name}"

    @staticmethod
    def with_random_key(name: str) -> AgentSessionId:
        return AgentSessionId(name=name, key=uuid.uuid4().hex)

    @property
    def entity_name(self) -> str:
        return self.to_entity_name(self.name)

    def __str__(self) -> str:
        return f"@{self.name}@{self.key}"

    def __repr__(self) -> str:
        return f"AgentSessionId(name='{self.name}', key='{self.key}')"

    @staticmethod
    def parse(session_id_string: str, agent_name: str | None = None) -> AgentSessionId:
        """Parses a string representation of an agent session ID.

        Args:
            session_id_string: A string in the form @name@key, or a plain key string
                when agent_name is provided.
            agent_name: Optional agent name to use instead of parsing from the string.
                If provided, only the key portion is extracted from session_id_string
                (for @name@key format) or the entire string is used as the key
                (for plain strings).

        Returns:
            AgentSessionId instance

        Raises:
            ValueError: If the string format is invalid and agent_name is not provided
        """
        # Check if string is in @name@key format
        if session_id_string.startswith("@") and "@" in session_id_string[1:]:
            parts = session_id_string[1:].split("@", 1)
            name = agent_name if agent_name is not None else parts[0]
            return AgentSessionId(name=name, key=parts[1])

        # Plain string format - only valid when agent_name is provided
        if agent_name is not None:
            return AgentSessionId(name=agent_name, key=session_id_string)

        raise ValueError(f"Invalid agent session ID format: {session_id_string}")


class DurableAgentThread(AgentThread):
    """Durable agent thread that tracks the owning :class:`AgentSessionId`."""

    _SERIALIZED_SESSION_ID_KEY = "durable_session_id"

    def __init__(
        self,
        *,
        session_id: AgentSessionId | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._session_id: AgentSessionId | None = session_id

    @property
    def session_id(self) -> AgentSessionId | None:
        return self._session_id

    @session_id.setter
    def session_id(self, value: AgentSessionId | None) -> None:
        self._session_id = value

    @classmethod
    def from_session_id(
        cls,
        session_id: AgentSessionId,
        **kwargs: Any,
    ) -> DurableAgentThread:
        return cls(session_id=session_id, **kwargs)

    async def serialize(self, **kwargs: Any) -> dict[str, Any]:
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

        thread.session_id = AgentSessionId.parse(session_id_value)
        return thread
