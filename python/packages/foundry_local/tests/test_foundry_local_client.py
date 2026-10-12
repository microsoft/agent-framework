# Copyright (c) Microsoft. All rights reserved.

import inspect
import json
from types import SimpleNamespace
from typing import Literal
from unittest.mock import MagicMock, patch

import httpx
import pytest
from agent_framework import Agent, SupportsChatGetResponse
from agent_framework._settings import load_settings
from agent_framework.exceptions import SettingNotFoundError
from agent_framework.foundry import FoundryLocalClient
from foundry_local_sdk import Configuration, DeviceType, IModel
from openai import AsyncOpenAI

from agent_framework_foundry_local._feature_usage import FeatureIndex
from agent_framework_foundry_local._foundry_local_client import FoundryLocalSettings


def test_foundry_local_owns_foundry_local_feature() -> None:
    assert FoundryLocalClient._FEATURE_USAGE_INDEX is FeatureIndex.FOUNDRY_LOCAL


def test_foundry_local_settings_init_from_env(foundry_local_unit_test_env: dict[str, str]) -> None:
    settings = load_settings(FoundryLocalSettings, env_prefix="FOUNDRY_LOCAL_")
    assert settings["model"] == foundry_local_unit_test_env["FOUNDRY_LOCAL_MODEL"]


def test_foundry_local_settings_init_with_explicit_values() -> None:
    settings = load_settings(FoundryLocalSettings, env_prefix="FOUNDRY_LOCAL_", model="custom-model-id")
    assert settings["model"] == "custom-model-id"


@pytest.mark.parametrize("exclude_list", [["FOUNDRY_LOCAL_MODEL"]], indirect=True)
def test_foundry_local_settings_missing_model(foundry_local_unit_test_env: dict[str, str]) -> None:
    with pytest.raises(SettingNotFoundError, match="Required setting 'model'"):
        load_settings(FoundryLocalSettings, env_prefix="FOUNDRY_LOCAL_", required_fields=["model"])


def test_foundry_local_settings_explicit_overrides_env(foundry_local_unit_test_env: dict[str, str]) -> None:
    settings = load_settings(FoundryLocalSettings, env_prefix="FOUNDRY_LOCAL_", model="override-model-id")
    assert settings["model"] == "override-model-id"
    assert settings["model"] != foundry_local_unit_test_env["FOUNDRY_LOCAL_MODEL"]


def test_foundry_local_client_init(mock_foundry_local_manager: MagicMock) -> None:
    client = FoundryLocalClient(model="test-model-id")

    assert client.model == "test-model-id"
    assert client.manager is mock_foundry_local_manager
    assert isinstance(client, SupportsChatGetResponse)
    assert str(client.client.base_url) == "http://localhost:5272/v1/"
    assert client.client.api_key == "foundry-local"


def test_agent_accepts_foundry_local_client(mock_foundry_local_manager: MagicMock) -> None:
    client = FoundryLocalClient(model="test-model-id")
    agent = Agent(client=client, instructions="test agent")
    assert agent.client is client


def test_foundry_local_client_get_response_uses_explicit_runtime_buckets() -> None:
    signature = inspect.signature(FoundryLocalClient.get_response)
    assert "client_kwargs" in signature.parameters
    assert "function_invocation_kwargs" in signature.parameters
    assert all(parameter.kind != inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values())


def test_foundry_local_client_initializes_singleton(mock_foundry_local_manager: MagicMock) -> None:
    with patch("agent_framework_foundry_local._foundry_local_client.FoundryLocalManager") as manager_class:
        manager_class.instance = None
        manager_class.initialize.side_effect = lambda _: setattr(manager_class, "instance", mock_foundry_local_manager)

        client = FoundryLocalClient(model="test-model-id")

        manager_class.initialize.assert_called_once()
        assert manager_class.initialize.call_args.args[0].app_name == "agent-framework"
        assert client.manager is mock_foundry_local_manager


def test_foundry_local_client_accepts_configuration(mock_foundry_local_manager: MagicMock) -> None:
    configuration = Configuration(app_name="my-app", model_cache_dir="my-models")
    with patch("agent_framework_foundry_local._foundry_local_client.FoundryLocalManager") as manager_class:
        manager_class.instance = None
        manager_class.initialize.side_effect = lambda _: setattr(manager_class, "instance", mock_foundry_local_manager)

        FoundryLocalClient(model="test-model-id", configuration=configuration)

        manager_class.initialize.assert_called_once_with(configuration)


def test_foundry_local_client_reuses_singleton(mock_foundry_local_manager: MagicMock) -> None:
    with patch("agent_framework_foundry_local._foundry_local_client.FoundryLocalManager") as manager_class:
        manager_class.instance = mock_foundry_local_manager
        FoundryLocalClient(model="test-model-id")
        FoundryLocalClient(model="test-model-id")
        manager_class.initialize.assert_not_called()
        mock_foundry_local_manager.start_web_service.assert_not_called()


def test_foundry_local_client_rejects_configuration_for_existing_manager(mock_foundry_local_manager: MagicMock) -> None:
    with pytest.raises(ValueError, match="already initialized"):
        FoundryLocalClient(model="test-model-id", configuration=Configuration(app_name="another-app"))


def test_foundry_local_client_bootstrap_false_requires_manager(mock_foundry_local_manager: MagicMock) -> None:
    with (
        patch("agent_framework_foundry_local._foundry_local_client.FoundryLocalManager") as manager_class,
        pytest.raises(ValueError, match="bootstrap=False"),
    ):
        manager_class.instance = None
        FoundryLocalClient(model="test-model-id", bootstrap=False)
    manager_class.initialize.assert_not_called()


def test_foundry_local_client_bootstrap_false_requires_service(mock_foundry_local_manager: MagicMock) -> None:
    mock_foundry_local_manager.urls = None
    with pytest.raises(ValueError, match="bootstrap=False"):
        FoundryLocalClient(model="test-model-id", bootstrap=False)
    mock_foundry_local_manager.start_web_service.assert_not_called()


def test_foundry_local_client_bootstrap_false_reuses_service(mock_foundry_local_manager: MagicMock) -> None:
    client = FoundryLocalClient(model="test-model-id", bootstrap=False)
    assert client.manager is mock_foundry_local_manager
    mock_foundry_local_manager.start_web_service.assert_not_called()


def test_foundry_local_client_starts_web_service(mock_foundry_local_manager: MagicMock) -> None:
    mock_foundry_local_manager.urls = None
    mock_foundry_local_manager.start_web_service.side_effect = lambda: setattr(
        mock_foundry_local_manager, "urls", ["http://127.0.0.1:4321/"]
    )
    client = FoundryLocalClient(model="test-model-id")
    mock_foundry_local_manager.start_web_service.assert_called_once_with()
    assert str(client.client.base_url) == "http://127.0.0.1:4321/v1/"


def test_foundry_local_client_requires_bound_url(mock_foundry_local_manager: MagicMock) -> None:
    mock_foundry_local_manager.urls = []
    with pytest.raises(ValueError, match="bound URL"):
        FoundryLocalClient(model="test-model-id")


def test_foundry_local_client_init_with_timeout(mock_foundry_local_manager: MagicMock) -> None:
    client = FoundryLocalClient(model="test-model-id", timeout=60.0)
    assert client.client.timeout == 60.0


def test_foundry_local_client_default_timeout(mock_foundry_local_manager: MagicMock) -> None:
    client = FoundryLocalClient(model="test-model-id")
    assert client.client.timeout is not None


def test_foundry_local_client_init_model_not_found(mock_foundry_local_manager: MagicMock) -> None:
    mock_foundry_local_manager.catalog.get_model.return_value = None
    with pytest.raises(ValueError, match="not found in Foundry Local"):
        FoundryLocalClient(model="unknown-model")


def test_foundry_local_client_uses_resolved_variant_id(mock_foundry_local_manager: MagicMock) -> None:
    mock_model = mock_foundry_local_manager.catalog.get_model_variant.return_value
    mock_model.id = "resolved-model-id:1"

    client = FoundryLocalClient(model="model-alias")

    assert client.model == "resolved-model-id:1"
    mock_foundry_local_manager.catalog.get_model_variant.assert_called_once_with("resolved-model-id:1")
    mock_model.download.assert_called_once_with()
    mock_model.load.assert_called_once_with()


def test_foundry_local_client_exact_id_does_not_resolve_alias(mock_foundry_local_manager: MagicMock) -> None:
    mock_model = mock_foundry_local_manager.catalog.get_model_variant.return_value
    mock_model.id = "exact-variant:1"

    client = FoundryLocalClient(model="exact-variant:1")

    assert client.model == "exact-variant:1"
    mock_foundry_local_manager.catalog.get_model_variant.assert_called_once_with("exact-variant:1")
    mock_foundry_local_manager.catalog.get_model.assert_not_called()


def test_foundry_local_client_init_from_env(
    foundry_local_unit_test_env: dict[str, str], mock_foundry_local_manager: MagicMock
) -> None:
    client = FoundryLocalClient()
    assert client.model == foundry_local_unit_test_env["FOUNDRY_LOCAL_MODEL"]


@pytest.mark.parametrize("device", [DeviceType.GPU, "GPU"])
def test_foundry_local_client_selects_device_variant(
    mock_foundry_local_manager: MagicMock, device: DeviceType | Literal["GPU"]
) -> None:
    mock_alias = mock_foundry_local_manager.catalog.get_model.return_value
    mock_gpu = MagicMock(spec=IModel)
    mock_gpu.id = "gpu-variant:1"
    mock_gpu.info = SimpleNamespace(runtime=SimpleNamespace(device_type=DeviceType.GPU))
    mock_alias.variants = [mock_foundry_local_manager.catalog.get_model_variant.return_value, mock_gpu]

    client = FoundryLocalClient(model="model-alias", device=device)

    assert client.model == "gpu-variant:1"
    mock_gpu.download.assert_called_once_with()
    mock_gpu.load.assert_called_once_with()
    mock_alias.select_variant.assert_not_called()


def test_foundry_local_client_exact_id_rejects_wrong_device(mock_foundry_local_manager: MagicMock) -> None:
    with pytest.raises(ValueError, match="exact-variant:1:GPU.*not found"):
        FoundryLocalClient(model="exact-variant:1", device=DeviceType.GPU)
    mock_foundry_local_manager.catalog.get_model.return_value.download.assert_not_called()


def test_foundry_local_client_missing_device_variant(mock_foundry_local_manager: MagicMock) -> None:
    with pytest.raises(ValueError, match="model-alias:GPU.*not found"):
        FoundryLocalClient(model="model-alias", device=DeviceType.GPU)


def test_foundry_local_client_unknown_runtime_does_not_match_device(mock_foundry_local_manager: MagicMock) -> None:
    mock_model = mock_foundry_local_manager.catalog.get_model_variant.return_value
    mock_model.info.runtime = None
    with pytest.raises(ValueError, match="model-alias:CPU.*not found"):
        FoundryLocalClient(model="model-alias", device=DeviceType.CPU)


def test_foundry_local_client_invalid_device(mock_foundry_local_manager: MagicMock) -> None:
    with pytest.raises(ValueError, match="DeviceType"):
        FoundryLocalClient(model="model-alias", device="invalid")  # pyright: ignore[reportArgumentType]
    mock_foundry_local_manager.catalog.get_model.assert_not_called()


def test_foundry_local_client_init_with_prepare_model_false(mock_foundry_local_manager: MagicMock) -> None:
    FoundryLocalClient(model="test-model-id", prepare_model=False)
    mock_model = mock_foundry_local_manager.catalog.get_model_variant.return_value
    mock_model.download.assert_not_called()
    mock_model.load.assert_not_called()


def test_foundry_local_client_does_not_hide_sdk_failure(mock_foundry_local_manager: MagicMock) -> None:
    mock_foundry_local_manager.catalog.get_model.side_effect = RuntimeError("catalog unavailable")
    with pytest.raises(RuntimeError, match="catalog unavailable"):
        FoundryLocalClient(model="model-alias")
    mock_foundry_local_manager.close.assert_not_called()


def test_foundry_local_client_closes_new_manager_on_failure(mock_foundry_local_manager: MagicMock) -> None:
    mock_foundry_local_manager.catalog.get_model.return_value = None
    with patch("agent_framework_foundry_local._foundry_local_client.FoundryLocalManager") as manager_class:
        manager_class.instance = None
        manager_class.initialize.side_effect = lambda _: setattr(manager_class, "instance", mock_foundry_local_manager)

        with pytest.raises(ValueError, match="not found in Foundry Local"):
            FoundryLocalClient(model="unknown-model")

    mock_foundry_local_manager.close.assert_called_once_with()


def test_foundry_local_client_keeps_new_manager_on_success(mock_foundry_local_manager: MagicMock) -> None:
    with patch("agent_framework_foundry_local._foundry_local_client.FoundryLocalManager") as manager_class:
        manager_class.instance = None
        manager_class.initialize.side_effect = lambda _: setattr(manager_class, "instance", mock_foundry_local_manager)

        FoundryLocalClient(model="test-model-id")

    mock_foundry_local_manager.close.assert_not_called()


def test_foundry_local_client_does_not_hide_web_service_failure(mock_foundry_local_manager: MagicMock) -> None:
    mock_foundry_local_manager.urls = None
    mock_foundry_local_manager.start_web_service.side_effect = RuntimeError("service unavailable")
    with pytest.raises(RuntimeError, match="service unavailable"):
        FoundryLocalClient(model="test-model-id")
    mock_foundry_local_manager.close.assert_not_called()


@pytest.mark.parametrize("stream", [False, True])
async def test_foundry_local_client_uses_openai_transport(mock_foundry_local_manager: MagicMock, stream: bool) -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        completion = {
            "id": "completion-1",
            "created": 0,
            "model": "test-model-id",
            "object": "chat.completion",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hello"}, "finish_reason": "stop"}],
        }
        if not stream:
            return httpx.Response(200, json=completion)
        completion["object"] = "chat.completion.chunk"
        completion["choices"] = [
            {"index": 0, "delta": {"role": "assistant", "content": "Hello"}, "finish_reason": "stop"}
        ]
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            text=f"data: {json.dumps(completion)}\n\ndata: [DONE]\n\n",
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http_client:
        async_client = AsyncOpenAI(
            base_url="http://localhost:5272/v1", api_key="foundry-local", http_client=http_client
        )
        with patch("agent_framework_foundry_local._foundry_local_client.AsyncOpenAI", return_value=async_client):
            client = FoundryLocalClient(model="test-model-id", prepare_model=False)
        if stream:
            result = "".join([update.text async for update in client.get_response("Hi", stream=True)])
        else:
            result = (await client.get_response("Hi")).text

    assert result == "Hello"
    assert len(requests) == 1
    assert requests[0].url.path == "/v1/chat/completions"
    payload = json.loads(requests[0].content)
    assert payload["model"] == "test-model-id"
    assert payload["stream"] is stream
