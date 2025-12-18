# Copyright (c) Microsoft. All rights reserved.

from unittest.mock import MagicMock, patch

import pytest
from agent_framework import ChatClientProtocol
from agent_framework.exceptions import ServiceInitializationError
from pydantic import ValidationError

from agent_framework_foundry_local import FoundryLocalClient
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
    """Test FoundryLocalClient initialization with mocked manager."""
    with patch(
        "agent_framework_foundry_local._foundry_local_client.FoundryLocalManager",
        return_value=mock_foundry_local_manager,
    ):
        client = FoundryLocalClient(model_id="test-model-id", env_file_path="test.env")

        assert client.model_id == "test-model-id"
        assert client.manager is mock_foundry_local_manager
        assert isinstance(client, ChatClientProtocol)


def test_foundry_local_client_init_with_bootstrap_false(mock_foundry_local_manager: MagicMock) -> None:
    """Test FoundryLocalClient initialization with bootstrap=False."""
    with patch(
        "agent_framework_foundry_local._foundry_local_client.FoundryLocalManager",
        return_value=mock_foundry_local_manager,
    ) as mock_manager_class:
        FoundryLocalClient(model_id="test-model-id", bootstrap=False, env_file_path="test.env")

        mock_manager_class.assert_called_once_with(
            bootstrap=False,
            timeout=None,
        )


def test_foundry_local_client_init_with_timeout(mock_foundry_local_manager: MagicMock) -> None:
    """Test FoundryLocalClient initialization with custom timeout."""
    with patch(
        "agent_framework_foundry_local._foundry_local_client.FoundryLocalManager",
        return_value=mock_foundry_local_manager,
    ) as mock_manager_class:
        FoundryLocalClient(model_id="test-model-id", timeout=60.0, env_file_path="test.env")

        mock_manager_class.assert_called_once_with(
            bootstrap=True,
            timeout=60.0,
        )


def test_foundry_local_client_init_model_not_found(mock_foundry_local_manager: MagicMock) -> None:
    """Test FoundryLocalClient initialization when model is not found."""
    mock_foundry_local_manager.get_model_info.return_value = None

    with (
        patch(
            "agent_framework_foundry_local._foundry_local_client.FoundryLocalManager",
            return_value=mock_foundry_local_manager,
        ),
        pytest.raises(ServiceInitializationError, match="not found in Foundry Local"),
    ):
        FoundryLocalClient(model_id="unknown-model", env_file_path="test.env")


def test_foundry_local_client_uses_model_info_id(mock_foundry_local_manager: MagicMock) -> None:
    """Test that client uses the model ID from model_info, not the alias."""
    mock_model_info = MagicMock()
    mock_model_info.id = "resolved-model-id"
    mock_foundry_local_manager.get_model_info.return_value = mock_model_info

    with patch(
        "agent_framework_foundry_local._foundry_local_client.FoundryLocalManager",
        return_value=mock_foundry_local_manager,
    ):
        client = FoundryLocalClient(model_id="model-alias", env_file_path="test.env")

        assert client.model_id == "resolved-model-id"


def test_foundry_local_client_init_from_env(
    foundry_local_unit_test_env: dict[str, str], mock_foundry_local_manager: MagicMock
) -> None:
    """Test FoundryLocalClient initialization using environment variables."""
    with patch(
        "agent_framework_foundry_local._foundry_local_client.FoundryLocalManager",
        return_value=mock_foundry_local_manager,
    ):
        client = FoundryLocalClient(env_file_path="test.env")

        assert client.model_id == foundry_local_unit_test_env["FOUNDRY_LOCAL_MODEL_ID"]


def test_foundry_local_client_init_with_device(mock_foundry_local_manager: MagicMock) -> None:
    """Test FoundryLocalClient initialization with device parameter."""
    from foundry_local.models import DeviceType

    with patch(
        "agent_framework_foundry_local._foundry_local_client.FoundryLocalManager",
        return_value=mock_foundry_local_manager,
    ):
        FoundryLocalClient(model_id="test-model-id", device=DeviceType.CPU, env_file_path="test.env")

        mock_foundry_local_manager.get_model_info.assert_called_once_with(
            alias_or_model_id="test-model-id",
            device=DeviceType.CPU,
        )
        mock_foundry_local_manager.download_model.assert_called_once_with(
            alias_or_model_id="test-model-id",
            device=DeviceType.CPU,
        )
        mock_foundry_local_manager.load_model.assert_called_once_with(
            alias_or_model_id="test-model-id",
            device=DeviceType.CPU,
        )


def test_foundry_local_client_init_model_not_found_with_device(mock_foundry_local_manager: MagicMock) -> None:
    """Test FoundryLocalClient error message includes device when model not found with device specified."""
    from foundry_local.models import DeviceType

    mock_foundry_local_manager.get_model_info.return_value = None

    with (
        patch(
            "agent_framework_foundry_local._foundry_local_client.FoundryLocalManager",
            return_value=mock_foundry_local_manager,
        ),
        pytest.raises(ServiceInitializationError, match="unknown-model:GPU.*not found"),
    ):
        FoundryLocalClient(model_id="unknown-model", device=DeviceType.GPU, env_file_path="test.env")


def test_foundry_local_client_init_with_prepare_model_false(mock_foundry_local_manager: MagicMock) -> None:
    """Test FoundryLocalClient initialization with prepare_model=False skips download and load."""
    with patch(
        "agent_framework_foundry_local._foundry_local_client.FoundryLocalManager",
        return_value=mock_foundry_local_manager,
    ):
        FoundryLocalClient(model_id="test-model-id", prepare_model=False, env_file_path="test.env")

        mock_foundry_local_manager.download_model.assert_not_called()
        mock_foundry_local_manager.load_model.assert_not_called()


def test_foundry_local_client_init_calls_download_and_load(mock_foundry_local_manager: MagicMock) -> None:
    """Test FoundryLocalClient initialization calls download_model and load_model by default."""
    with patch(
        "agent_framework_foundry_local._foundry_local_client.FoundryLocalManager",
        return_value=mock_foundry_local_manager,
    ):
        FoundryLocalClient(model_id="test-model-id", env_file_path="test.env")

        mock_foundry_local_manager.download_model.assert_called_once_with(
            alias_or_model_id="test-model-id",
            device=None,
        )
        mock_foundry_local_manager.load_model.assert_called_once_with(
            alias_or_model_id="test-model-id",
            device=None,
        )
