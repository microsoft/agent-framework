# Copyright (c) Microsoft. All rights reserved.

from unittest.mock import MagicMock, patch

import pytest
from agent_framework import ChatClientProtocol
from agent_framework.exceptions import ServiceInitializationError
from pydantic import ValidationError

from agent_framework_foundry_local import FoundryLocalChatClient
from agent_framework_foundry_local._foundry_local_client import FoundryLocalSettings

# Settings Tests


def test_foundry_local_settings_init_from_env(foundry_local_unit_test_env: dict[str, str]) -> None:
    """Test FoundryLocalSettings initialization from environment variables."""
    settings = FoundryLocalSettings(env_file_path="test.env")

    assert settings.model_id == foundry_local_unit_test_env["FOUNDRY_LOCAL_MODEL_ID"]


def test_foundry_local_settings_init_with_explicit_values() -> None:
    """Test FoundryLocalSettings initialization with explicit values."""
    settings = FoundryLocalSettings(model_id="custom-model-id", env_file_path="test.env")

    assert settings.model_id == "custom-model-id"


@pytest.mark.parametrize("exclude_list", [["FOUNDRY_LOCAL_MODEL_ID"]], indirect=True)
def test_foundry_local_settings_missing_model_id(foundry_local_unit_test_env: dict[str, str]) -> None:
    """Test FoundryLocalSettings when model_id is missing raises ValidationError."""
    with pytest.raises(ValidationError):
        FoundryLocalSettings(env_file_path="test.env")


def test_foundry_local_settings_explicit_overrides_env(foundry_local_unit_test_env: dict[str, str]) -> None:
    """Test that explicit values override environment variables."""
    settings = FoundryLocalSettings(model_id="override-model-id", env_file_path="test.env")

    assert settings.model_id == "override-model-id"
    assert settings.model_id != foundry_local_unit_test_env["FOUNDRY_LOCAL_MODEL_ID"]


# Client Initialization Tests


def test_foundry_local_client_init(mock_foundry_local_manager: MagicMock) -> None:
    """Test FoundryLocalChatClient initialization with mocked manager."""
    with patch(
        "agent_framework_foundry_local._foundry_local_client.FoundryLocalManager",
        return_value=mock_foundry_local_manager,
    ):
        client = FoundryLocalChatClient(model_id="test-model-id", env_file_path="test.env")

        assert client.model_id == "test-model-id"
        assert client.manager is mock_foundry_local_manager
        assert isinstance(client, ChatClientProtocol)


def test_foundry_local_client_init_with_bootstrap_false(mock_foundry_local_manager: MagicMock) -> None:
    """Test FoundryLocalChatClient initialization with bootstrap=False."""
    with patch(
        "agent_framework_foundry_local._foundry_local_client.FoundryLocalManager",
        return_value=mock_foundry_local_manager,
    ) as mock_manager_class:
        FoundryLocalChatClient(model_id="test-model-id", bootstrap=False, env_file_path="test.env")

        mock_manager_class.assert_called_once_with(
            alias_or_model_id="test-model-id",
            bootstrap=False,
            timeout=None,
        )


def test_foundry_local_client_init_with_timeout(mock_foundry_local_manager: MagicMock) -> None:
    """Test FoundryLocalChatClient initialization with custom timeout."""
    with patch(
        "agent_framework_foundry_local._foundry_local_client.FoundryLocalManager",
        return_value=mock_foundry_local_manager,
    ) as mock_manager_class:
        FoundryLocalChatClient(model_id="test-model-id", timeout=60.0, env_file_path="test.env")

        mock_manager_class.assert_called_once_with(
            alias_or_model_id="test-model-id",
            bootstrap=True,
            timeout=60.0,
        )


def test_foundry_local_client_init_model_not_found(mock_foundry_local_manager: MagicMock) -> None:
    """Test FoundryLocalChatClient initialization when model is not found."""
    mock_foundry_local_manager.get_model_info.return_value = None

    with (
        patch(
            "agent_framework_foundry_local._foundry_local_client.FoundryLocalManager",
            return_value=mock_foundry_local_manager,
        ),
        pytest.raises(ServiceInitializationError, match="not found in Foundry Local"),
    ):
        FoundryLocalChatClient(model_id="unknown-model", env_file_path="test.env")


def test_foundry_local_client_uses_model_info_id(mock_foundry_local_manager: MagicMock) -> None:
    """Test that client uses the model ID from model_info, not the alias."""
    mock_model_info = MagicMock()
    mock_model_info.id = "resolved-model-id"
    mock_foundry_local_manager.get_model_info.return_value = mock_model_info

    with patch(
        "agent_framework_foundry_local._foundry_local_client.FoundryLocalManager",
        return_value=mock_foundry_local_manager,
    ):
        client = FoundryLocalChatClient(model_id="model-alias", env_file_path="test.env")

        assert client.model_id == "resolved-model-id"


def test_foundry_local_client_init_from_env(
    foundry_local_unit_test_env: dict[str, str], mock_foundry_local_manager: MagicMock
) -> None:
    """Test FoundryLocalChatClient initialization using environment variables."""
    with patch(
        "agent_framework_foundry_local._foundry_local_client.FoundryLocalManager",
        return_value=mock_foundry_local_manager,
    ):
        client = FoundryLocalChatClient(env_file_path="test.env")

        assert client.model_id == foundry_local_unit_test_env["FOUNDRY_LOCAL_MODEL_ID"]
