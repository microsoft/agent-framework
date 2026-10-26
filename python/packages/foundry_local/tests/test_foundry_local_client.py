# Copyright (c) Microsoft. All rights reserved.

import inspect
import threading
import time
from unittest.mock import MagicMock, patch

import pytest
from agent_framework import Agent, SupportsChatGetResponse
from agent_framework._settings import load_settings
from agent_framework.exceptions import SettingNotFoundError
from agent_framework.foundry import FoundryLocalClient
from foundry_local_sdk import DeviceType

from agent_framework_foundry_local._feature_usage import FeatureIndex
from agent_framework_foundry_local._foundry_local_client import (
    FoundryLocalSettings,
    _resolve_foundry_local_manager,
)

# Settings Tests


def test_foundry_local_owns_foundry_local_feature() -> None:
    assert FoundryLocalClient._FEATURE_USAGE_INDEX is FeatureIndex.FOUNDRY_LOCAL


def test_foundry_local_settings_init_from_env(foundry_local_unit_test_env: dict[str, str]) -> None:
    """Test FoundryLocalSettings initialization from environment variables."""
    settings = load_settings(FoundryLocalSettings, env_prefix="FOUNDRY_LOCAL_")

    assert settings["model"] == foundry_local_unit_test_env["FOUNDRY_LOCAL_MODEL"]


def test_foundry_local_settings_init_with_explicit_values() -> None:
    """Test FoundryLocalSettings initialization with explicit values."""
    settings = load_settings(
        FoundryLocalSettings,
        env_prefix="FOUNDRY_LOCAL_",
        model="custom-model-id",
    )

    assert settings["model"] == "custom-model-id"


@pytest.mark.parametrize("exclude_list", [["FOUNDRY_LOCAL_MODEL"]], indirect=True)
def test_foundry_local_settings_missing_model(foundry_local_unit_test_env: dict[str, str]) -> None:
    """Test FoundryLocalSettings when model is missing raises error."""
    with pytest.raises(SettingNotFoundError, match="Required setting 'model'"):
        load_settings(
            FoundryLocalSettings,
            env_prefix="FOUNDRY_LOCAL_",
            required_fields=["model"],
        )


def test_foundry_local_settings_explicit_overrides_env(foundry_local_unit_test_env: dict[str, str]) -> None:
    """Test that explicit values override environment variables."""
    settings = load_settings(FoundryLocalSettings, env_prefix="FOUNDRY_LOCAL_", model="override-model-id")

    assert settings["model"] == "override-model-id"
    assert settings["model"] != foundry_local_unit_test_env["FOUNDRY_LOCAL_MODEL"]


# Client Initialization Tests


def test_foundry_local_client_init(mock_foundry_local_manager: MagicMock) -> None:
    """Test FoundryLocalClient initialization with mocked manager."""
    with patch(
        "agent_framework_foundry_local._foundry_local_client._resolve_foundry_local_manager",
        return_value=mock_foundry_local_manager,
    ):
        client = FoundryLocalClient(model="test-model-id")

        assert client.model == "test-model-id"
        assert client.manager is mock_foundry_local_manager
        assert isinstance(client, SupportsChatGetResponse)


def test_agent_accepts_foundry_local_client(mock_foundry_local_manager: MagicMock) -> None:
    with patch(
        "agent_framework_foundry_local._foundry_local_client._resolve_foundry_local_manager",
        return_value=mock_foundry_local_manager,
    ):
        client = FoundryLocalClient(model="test-model-id")

    agent = Agent(client=client, instructions="test agent")
    assert agent.client is client


def test_foundry_local_client_get_response_uses_explicit_runtime_buckets() -> None:
    """Foundry Local should expose explicit runtime buckets instead of raw kwargs."""
    signature = inspect.signature(FoundryLocalClient.get_response)

    assert "client_kwargs" in signature.parameters
    assert "function_invocation_kwargs" in signature.parameters
    assert all(parameter.kind != inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values())


def test_foundry_local_client_init_with_bootstrap_false(mock_foundry_local_manager: MagicMock) -> None:
    """Test that bootstrap=False leaves an already running web service alone."""
    with patch(
        "agent_framework_foundry_local._foundry_local_client._resolve_foundry_local_manager",
        return_value=mock_foundry_local_manager,
    ):
        FoundryLocalClient(model="test-model-id", bootstrap=False)

        mock_foundry_local_manager.start_web_service.assert_not_called()


def test_foundry_local_client_starts_web_service_when_not_running(mock_foundry_local_manager: MagicMock) -> None:
    """Test that bootstrap=True starts the web service when it is not already up."""
    mock_foundry_local_manager.urls = None

    def _start() -> None:
        mock_foundry_local_manager.urls = ["http://localhost:5272"]

    mock_foundry_local_manager.start_web_service.side_effect = _start

    with patch(
        "agent_framework_foundry_local._foundry_local_client._resolve_foundry_local_manager",
        return_value=mock_foundry_local_manager,
    ):
        FoundryLocalClient(model="test-model-id")

        mock_foundry_local_manager.start_web_service.assert_called_once_with()


def test_foundry_local_client_requires_endpoint_when_bootstrap_false(mock_foundry_local_manager: MagicMock) -> None:
    """Test that a client without a running web service fails with an actionable error."""
    mock_foundry_local_manager.urls = None

    with (
        patch(
            "agent_framework_foundry_local._foundry_local_client._resolve_foundry_local_manager",
            return_value=mock_foundry_local_manager,
        ),
        pytest.raises(ValueError, match="web service is not running"),
    ):
        FoundryLocalClient(model="test-model-id", bootstrap=False)


def test_foundry_local_client_uses_web_service_base_url(mock_foundry_local_manager: MagicMock) -> None:
    """Test that the OpenAI client points at the web service's OpenAI-compatible route."""
    mock_foundry_local_manager.urls = ["http://localhost:5272"]

    with patch(
        "agent_framework_foundry_local._foundry_local_client._resolve_foundry_local_manager",
        return_value=mock_foundry_local_manager,
    ):
        client = FoundryLocalClient(model="test-model-id")

        # httpx normalizes the base URL with a trailing slash.
        assert str(client.client.base_url).rstrip("/") == "http://localhost:5272/v1"


def test_foundry_local_client_init_with_timeout(mock_foundry_local_manager: MagicMock) -> None:
    """Test FoundryLocalClient initialization with custom timeout."""
    with patch(
        "agent_framework_foundry_local._foundry_local_client._resolve_foundry_local_manager",
        return_value=mock_foundry_local_manager,
    ):
        client = FoundryLocalClient(model="test-model-id", timeout=60.0)

        assert client.client.timeout == 60.0


def test_foundry_local_client_init_model_not_found(mock_foundry_local_manager: MagicMock) -> None:
    """Test FoundryLocalClient initialization when model is not found."""
    mock_foundry_local_manager.catalog.get_model.return_value = None

    with (
        patch(
            "agent_framework_foundry_local._foundry_local_client._resolve_foundry_local_manager",
            return_value=mock_foundry_local_manager,
        ),
        pytest.raises(ValueError, match="not found in Foundry Local"),
    ):
        FoundryLocalClient(model="unknown-model")


def test_foundry_local_client_resolves_full_model_id(mock_foundry_local_manager: MagicMock) -> None:
    """Test that a full model ID resolves through the variant lookup when the alias misses."""
    variant = MagicMock()
    variant.id = "test-model-id-generic-cpu:1"
    mock_foundry_local_manager.catalog.get_model.return_value = None
    mock_foundry_local_manager.catalog.get_model_variant.return_value = variant

    with patch(
        "agent_framework_foundry_local._foundry_local_client._resolve_foundry_local_manager",
        return_value=mock_foundry_local_manager,
    ):
        client = FoundryLocalClient(model="test-model-id-generic-cpu:1")

        mock_foundry_local_manager.catalog.get_model_variant.assert_called_once_with("test-model-id-generic-cpu:1")
        assert client.model == "test-model-id-generic-cpu:1"


def test_foundry_local_client_uses_model_id(mock_foundry_local_manager: MagicMock) -> None:
    """Test that client uses the model ID from the catalog, not the alias."""
    mock_foundry_local_manager.catalog.get_model.return_value.id = "resolved-model-id"

    with patch(
        "agent_framework_foundry_local._foundry_local_client._resolve_foundry_local_manager",
        return_value=mock_foundry_local_manager,
    ):
        client = FoundryLocalClient(model="model-alias")

        assert client.model == "resolved-model-id"


def test_foundry_local_client_init_from_env(
    foundry_local_unit_test_env: dict[str, str], mock_foundry_local_manager: MagicMock
) -> None:
    """Test FoundryLocalClient initialization using environment variables."""
    mock_foundry_local_manager.catalog.get_model.return_value.id = foundry_local_unit_test_env["FOUNDRY_LOCAL_MODEL"]

    with patch(
        "agent_framework_foundry_local._foundry_local_client._resolve_foundry_local_manager",
        return_value=mock_foundry_local_manager,
    ):
        client = FoundryLocalClient()

        assert client.model == foundry_local_unit_test_env["FOUNDRY_LOCAL_MODEL"]


def test_foundry_local_client_init_with_device(
    mock_foundry_local_manager: MagicMock, mock_foundry_local_model: MagicMock
) -> None:
    """Test FoundryLocalClient initialization with device parameter."""
    cpu_variant = MagicMock()
    cpu_variant.info.runtime.device_type = DeviceType.CPU
    gpu_variant = MagicMock()
    gpu_variant.info.runtime.device_type = DeviceType.GPU
    mock_foundry_local_model.variants = [cpu_variant, gpu_variant]

    with patch(
        "agent_framework_foundry_local._foundry_local_client._resolve_foundry_local_manager",
        return_value=mock_foundry_local_manager,
    ):
        FoundryLocalClient(model="test-model-id", device=DeviceType.GPU)

        mock_foundry_local_model.select_variant.assert_called_once_with(gpu_variant)


def test_foundry_local_client_init_model_not_found_with_device(
    mock_foundry_local_manager: MagicMock, mock_foundry_local_model: MagicMock
) -> None:
    """Test FoundryLocalClient error message includes device when no variant matches."""
    cpu_variant = MagicMock()
    cpu_variant.info.runtime.device_type = DeviceType.CPU
    mock_foundry_local_model.variants = [cpu_variant]

    with (
        patch(
            "agent_framework_foundry_local._foundry_local_client._resolve_foundry_local_manager",
            return_value=mock_foundry_local_manager,
        ),
        pytest.raises(ValueError, match="unknown-model:GPU.*not found"),
    ):
        FoundryLocalClient(model="unknown-model", device=DeviceType.GPU)


def test_foundry_local_client_init_with_prepare_model_false(
    mock_foundry_local_manager: MagicMock, mock_foundry_local_model: MagicMock
) -> None:
    """Test FoundryLocalClient initialization with prepare_model=False skips download and load."""
    with patch(
        "agent_framework_foundry_local._foundry_local_client._resolve_foundry_local_manager",
        return_value=mock_foundry_local_manager,
    ):
        FoundryLocalClient(model="test-model-id", prepare_model=False)

        mock_foundry_local_model.download.assert_not_called()
        mock_foundry_local_model.load.assert_not_called()


def test_foundry_local_client_init_calls_download_and_load(
    mock_foundry_local_manager: MagicMock, mock_foundry_local_model: MagicMock
) -> None:
    """Test FoundryLocalClient initialization downloads and loads the model by default."""
    with patch(
        "agent_framework_foundry_local._foundry_local_client._resolve_foundry_local_manager",
        return_value=mock_foundry_local_manager,
    ):
        FoundryLocalClient(model="test-model-id")

        mock_foundry_local_model.download.assert_called_once_with()
        mock_foundry_local_model.load.assert_called_once_with()


def test_foundry_local_client_registers_execution_providers_for_accelerated_device(
    mock_foundry_local_manager: MagicMock, mock_foundry_local_model: MagicMock
) -> None:
    """Accelerated variants only exist in the catalog once their provider is registered."""
    gpu_variant = MagicMock()
    gpu_variant.info.runtime.device_type = DeviceType.GPU
    mock_foundry_local_model.variants = [gpu_variant]

    with patch(
        "agent_framework_foundry_local._foundry_local_client._resolve_foundry_local_manager",
        return_value=mock_foundry_local_manager,
    ):
        FoundryLocalClient(model="test-model-id", device=DeviceType.GPU)

        mock_foundry_local_manager.download_and_register_eps.assert_called_once_with()


def test_foundry_local_client_skips_execution_providers_for_cpu(
    mock_foundry_local_manager: MagicMock, mock_foundry_local_model: MagicMock
) -> None:
    """An explicit CPU request should not download accelerated providers it will not use."""
    cpu_variant = MagicMock()
    cpu_variant.info.runtime.device_type = DeviceType.CPU
    mock_foundry_local_model.variants = [cpu_variant]

    with patch(
        "agent_framework_foundry_local._foundry_local_client._resolve_foundry_local_manager",
        return_value=mock_foundry_local_manager,
    ):
        FoundryLocalClient(model="test-model-id", device=DeviceType.CPU)

        mock_foundry_local_manager.download_and_register_eps.assert_not_called()
        mock_foundry_local_model.select_variant.assert_called_once_with(cpu_variant)


def test_resolve_manager_initializes_once_under_concurrency() -> None:
    """Two threads racing on first use must share one manager, not fail the second one."""
    manager = MagicMock()
    initialize_calls: list[int] = []
    gate = threading.Barrier(2)

    def _initialize(config: object) -> None:
        initialize_calls.append(1)
        # The SDK rejects a second initialization, so a race must never reach here twice.
        assert len(initialize_calls) == 1
        # Widen the window so both threads observe the uninitialized singleton.
        time.sleep(0.05)
        fake_manager_class.instance = manager

    fake_manager_class = MagicMock()
    fake_manager_class.instance = None
    fake_manager_class.initialize.side_effect = _initialize

    resolved: list[object] = []

    def _worker() -> None:
        gate.wait()
        resolved.append(_resolve_foundry_local_manager())

    with patch("agent_framework_foundry_local._foundry_local_client.FoundryLocalManager", fake_manager_class):
        threads = [threading.Thread(target=_worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

    assert len(initialize_calls) == 1
    assert resolved == [manager, manager]
