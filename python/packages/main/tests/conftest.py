# Copyright (c) Microsoft. All rights reserved.
import os
from typing import Any

from pydantic import BaseModel
from pytest import fixture

from agent_framework import AITool, ChatMessage, ai_function


# region: Connector Settings fixtures
@fixture
def exclude_list(request: Any) -> list[str]:
    """Fixture that returns a list of environment variables to exclude."""
    return request.param if hasattr(request, "param") else []


@fixture
def override_env_param_dict(request: Any) -> dict[str, str]:
    """Fixture that returns a dict of environment variables to override."""
    return request.param if hasattr(request, "param") else {}


@fixture()
def openai_unit_test_env(monkeypatch, exclude_list, override_env_param_dict):  # type: ignore
    """Fixture to set environment variables for OpenAISettings."""
    if exclude_list is None:
        exclude_list = []

    if override_env_param_dict is None:
        override_env_param_dict = {}

    env_vars = {
        "OPENAI_ORG_ID": "test_org_id",
        "OPENAI_RESPONSES_MODEL_ID": "test_responses_model_id",
        "OPENAI_CHAT_MODEL_ID": "test_chat_model_id",
        "OPENAI_TEXT_MODEL_ID": "test_text_model_id",
        "OPENAI_EMBEDDING_MODEL_ID": "test_embedding_model_id",
        "OPENAI_TEXT_TO_IMAGE_MODEL_ID": "test_text_to_image_model_id",
        "OPENAI_AUDIO_TO_TEXT_MODEL_ID": "test_audio_to_text_model_id",
        "OPENAI_TEXT_TO_AUDIO_MODEL_ID": "test_text_to_audio_model_id",
        "OPENAI_REALTIME_MODEL_ID": "test_realtime_model_id",
    }

    env_vars.update(override_env_param_dict)  # type: ignore

    for key, value in env_vars.items():
        if key not in exclude_list:
            monkeypatch.setenv(key, value)  # type: ignore
        else:
            monkeypatch.delenv(key, raising=False)  # type: ignore

    if not os.getenv("OPENAI_API_KEY"):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-dummy-key")  # type: ignore
    if "OPENAI_API_KEY" in exclude_list:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)  # type: ignore
    env_vars["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY", "sk-test-dummy-key")
    return env_vars


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
