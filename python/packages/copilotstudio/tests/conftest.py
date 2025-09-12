# Copyright (c) Microsoft. All rights reserved.

from typing import Any
from unittest.mock import MagicMock

import pytest
from microsoft_agents.copilotstudio.client import CopilotClient


@pytest.fixture
def exclude_list(request: Any) -> list[str]:
    """Fixture that returns a list of environment variables to exclude."""
    return request.param if hasattr(request, "param") else []


@pytest.fixture
def override_env_param_dict(request: Any) -> dict[str, str]:
    """Fixture that returns a dict of environment variables to override."""
    return request.param if hasattr(request, "param") else {}


@pytest.fixture()
def copilot_studio_unit_test_env(monkeypatch, exclude_list, override_env_param_dict):  # type: ignore
    """Fixture to set environment variables for CopilotStudioSettings."""

    if exclude_list is None:
        exclude_list = []

    if override_env_param_dict is None:
        override_env_param_dict = {}

    env_vars = {
        "COPILOTSTUDIOAGENT__ENVIRONMENTID": "test-environment-id",
        "COPILOTSTUDIOAGENT__SCHEMANAME": "test-schema-name",
        "COPILOTSTUDIOAGENT__AGENTAPPID": "test-client-id",
        "COPILOTSTUDIOAGENT__TENANTID": "test-tenant-id",
    }

    env_vars.update(override_env_param_dict)  # type: ignore

    for key, value in env_vars.items():
        if key in exclude_list:
            monkeypatch.delenv(key, raising=False)  # type: ignore
            continue
        monkeypatch.setenv(key, value)  # type: ignore

    return env_vars


@pytest.fixture
def mock_copilot_client() -> MagicMock:
    """Mock CopilotClient for testing."""
    return MagicMock(spec=CopilotClient)


@pytest.fixture
def mock_pca() -> MagicMock:
    """Mock PublicClientApplication for testing."""
    mock_pca = MagicMock()

    # Mock successful token response
    mock_token_response = {
        "access_token": "test-access-token-12345",
        "token_type": "Bearer",
        "expires_in": 3600,
    }

    mock_pca.get_accounts.return_value = []
    mock_pca.acquire_token_interactive.return_value = mock_token_response
    mock_pca.acquire_token_silent.return_value = mock_token_response

    return mock_pca


@pytest.fixture
def mock_activity() -> MagicMock:
    """Mock Activity for testing."""
    mock_activity = MagicMock()
    mock_activity.text = "Test response"
    mock_activity.type = "message"
    mock_activity.id = "test-activity-id"
    mock_activity.from_property.name = "Test Bot"
    return mock_activity


@pytest.fixture
def mock_conversation() -> MagicMock:
    """Mock conversation for testing."""
    mock_conversation = MagicMock()
    mock_conversation.id = "test-conversation-id"
    return mock_conversation
