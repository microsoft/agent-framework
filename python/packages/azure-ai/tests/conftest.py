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


@fixture()
def azure_ai_unit_test_env(monkeypatch, exclude_list, override_env_param_dict):  # type: ignore
    """Fixture to set environment variables for AzureAISettings."""

    if exclude_list is None:
        exclude_list = []

    if override_env_param_dict is None:
        override_env_param_dict = {}

    env_vars = {
        "AZURE_AI_PROJECT_ENDPOINT": "https://test-project.cognitiveservices.azure.com/",
        "AZURE_AI_MODEL_DEPLOYMENT_NAME": "test-gpt-4o",
    }

    env_vars.update(override_env_param_dict)  # type: ignore

    for key, value in env_vars.items():
        if key in exclude_list:
            monkeypatch.delenv(key, raising=False)  # type: ignore
            continue
        monkeypatch.setenv(key, value)  # type: ignore

    return env_vars


@fixture
def mock_agents_client() -> MagicMock:
    """Fixture that provides a mock AgentsClient."""
    mock_client = MagicMock()

    # Mock agents property
    mock_client.create_agent = AsyncMock()
    mock_client.delete_agent = AsyncMock()

    # Mock agent creation response
    mock_agent = MagicMock()
    mock_agent.id = "test-agent-id"
    mock_client.create_agent.return_value = mock_agent

    # Mock threads property
    mock_client.threads = MagicMock()
    mock_client.threads.create = AsyncMock()
    mock_client.messages.create = AsyncMock()

    # Mock runs property
    mock_client.runs = MagicMock()
    mock_client.runs.list = AsyncMock()
    mock_client.runs.cancel = AsyncMock()
    mock_client.runs.stream = AsyncMock()
    mock_client.runs.submit_tool_outputs_stream = AsyncMock()

    return mock_client


@fixture
def mock_azure_credential() -> MagicMock:
    """Fixture that provides a mock AsyncTokenCredential."""
    return MagicMock()
