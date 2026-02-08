# Copyright (c) Microsoft. All rights reserved.
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from pytest import fixture


@fixture
def exclude_list(request: Any) -> list[str]:
    """Fixture that returns a list of environment variables to exclude."""
    return request.param if hasattr(request, "param") else []


@fixture
def override_env_param_dict(request: Any) -> dict[str, str]:
    """Fixture that returns a dict of environment variables to override."""
    return request.param if hasattr(request, "param") else {}


@fixture
def anthropic_unit_test_env(monkeypatch, exclude_list, override_env_param_dict):  # type: ignore
    """Fixture to set environment variables for AnthropicSettings."""
    if exclude_list is None:
        exclude_list = []

    if override_env_param_dict is None:
        override_env_param_dict = {}

    env_vars = {
        "ANTHROPIC_API_KEY": "test-api-key-12345",
        "ANTHROPIC_CHAT_MODEL_ID": "claude-3-5-sonnet-20241022",
    }

    env_vars.update(override_env_param_dict)  # type: ignore

    for key, value in env_vars.items():
        if key in exclude_list:
            monkeypatch.delenv(key, raising=False)  # type: ignore
            continue
        monkeypatch.setenv(key, value)  # type: ignore

    return env_vars


@fixture
def mock_anthropic_client() -> MagicMock:
    """Fixture that provides a mock AsyncAnthropic client."""
    mock_client = MagicMock()
    mock_client.base_url = "https://api.anthropic.com"

    # Mock beta.messages property
    mock_client.beta = MagicMock()
    mock_client.beta.messages = MagicMock()
    mock_client.beta.messages.create = AsyncMock()

    return mock_client
