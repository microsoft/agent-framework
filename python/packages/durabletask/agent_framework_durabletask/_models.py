# Copyright (c) Microsoft. All rights reserved.

"""Data models for Durable Agent Framework.

This module defines the request and response models used by the framework.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from datetime import datetime
from importlib import import_module
from typing import TYPE_CHECKING, Any, cast

from agent_framework import Role

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
        correlation_id: Optional correlation ID for tracking the response to this specific request
        created_at: Optional timestamp when the request was created
        orchestration_id: Optional ID of the orchestration that initiated this request
    """

    message: str
    request_response_format: str
    role: Role = Role.USER
    response_format: type[BaseModel] | None = None
    enable_tool_calls: bool = True
    correlation_id: str | None = None
    created_at: datetime | None = None
    orchestration_id: str | None = None

    def __init__(
        self,
        message: str,
        request_response_format: str = REQUEST_RESPONSE_FORMAT_TEXT,
        role: Role | str | None = Role.USER,
        response_format: type[BaseModel] | None = None,
        enable_tool_calls: bool = True,
        correlation_id: str | None = None,
        created_at: datetime | None = None,
        orchestration_id: str | None = None,
    ) -> None:
        self.message = message
        self.role = self.coerce_role(role)
        self.response_format = response_format
        self.request_response_format = request_response_format
        self.enable_tool_calls = enable_tool_calls
        self.correlation_id = correlation_id
        self.created_at = created_at
        self.orchestration_id = orchestration_id

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
            "request_response_format": self.request_response_format,
        }
        if self.response_format:
            result["response_format"] = serialize_response_format(self.response_format)
        if self.correlation_id:
            result["correlationId"] = self.correlation_id
        if self.created_at:
            result["created_at"] = self.created_at.isoformat()
        if self.orchestration_id:
            result["orchestrationId"] = self.orchestration_id

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunRequest:
        """Create RunRequest from dictionary."""
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            try:
                created_at = datetime.fromisoformat(created_at)
            except ValueError:
                created_at = None

        return cls(
            message=data.get("message", ""),
            request_response_format=data.get("request_response_format", REQUEST_RESPONSE_FORMAT_TEXT),
            role=cls.coerce_role(data.get("role")),
            response_format=_deserialize_response_format(data.get("response_format")),
            enable_tool_calls=data.get("enable_tool_calls", True),
            correlation_id=data.get("correlationId"),
            created_at=created_at,
            orchestration_id=data.get("orchestrationId"),
        )
