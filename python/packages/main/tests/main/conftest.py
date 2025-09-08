# Copyright (c) Microsoft. All rights reserved.
from typing import Any

from pydantic import BaseModel
from pytest import fixture

from agent_framework import ChatMessage, ToolProtocol, ai_function
from agent_framework.telemetry import OtelSettings


@fixture(scope="function")
def chat_history() -> list[ChatMessage]:
    return []


@fixture
def ai_tool() -> ToolProtocol:
    """Returns a generic ToolProtocol."""

    class GenericTool(BaseModel):
        name: str
        description: str | None = None
        additional_properties: dict[str, Any] | None = None

        def parameters(self) -> dict[str, Any]:
            """Return the parameters of the tool as a JSON schema."""
            return {
                "name": {"type": "string"},
            }

    return GenericTool(name="generic_tool", description="A generic tool")


@fixture
def ai_function_tool() -> ToolProtocol:
    """Returns a executable ToolProtocol."""

    @ai_function
    def simple_function(x: int, y: int) -> int:
        """A simple function that adds two numbers."""
        return x + y

    return simple_function


# region Otel Settings fixtures
@fixture
def enabled(request: Any) -> bool:
    """Fixture that returns a boolean indicating if Otel is enabled."""
    return request.param if hasattr(request, "param") else True


@fixture
def sensitive(request: Any) -> bool:
    """Fixture that returns a boolean indicating if sensitive data is enabled."""
    return request.param if hasattr(request, "param") else False


@fixture
def otel_settings(enabled: bool, sensitive: bool) -> OtelSettings:
    """Fixture to set environment variables for OtelSettings."""

    from agent_framework.telemetry import OTEL_SETTINGS, setup_telemetry

    setup_telemetry(enable_otel=enabled, enable_sensitive_data=sensitive)

    return OTEL_SETTINGS
