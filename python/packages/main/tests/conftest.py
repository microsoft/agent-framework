# Copyright (c) Microsoft. All rights reserved.
from typing import Any

from pydantic import BaseModel
from pytest import fixture

from agent_framework import AITool, ChatMessage, ai_function


@fixture(scope="function")
def chat_history() -> list[ChatMessage]:
    return []


@fixture
def ai_tool() -> AITool:
    """Returns a generic AITool."""

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
def ai_function_tool() -> AITool:
    """Returns a executable AITool."""

    @ai_function
    def simple_function(x: int, y: int) -> int:
        """A simple function that adds two numbers."""
        return x + y

    return simple_function
