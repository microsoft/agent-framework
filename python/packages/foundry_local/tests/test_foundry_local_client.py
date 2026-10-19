# Copyright (c) Microsoft. All rights reserved.

import asyncio
import inspect
import json
from collections.abc import AsyncGenerator, Awaitable, Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from copy import deepcopy
from importlib import import_module
from queue import Queue
from threading import Event, Lock, get_ident
from types import SimpleNamespace
from typing import Any, Literal, cast
from unittest.mock import MagicMock, patch

import pytest
from agent_framework import (
    Agent,
    ChatAndFunctionMiddlewareTypes,
    ChatContext,
    ChatOptions,
    Content,
    FunctionInvocationConfiguration,
    Message,
    SupportsChatGetResponse,
    chat_middleware,
    tool,
)
from agent_framework._settings import load_settings
from agent_framework.exceptions import ChatClientException, SettingNotFoundError
from agent_framework.foundry import FoundryLocalChatOptions, FoundryLocalClient
from agent_framework_openai import RawOpenAIChatCompletionClient
from foundry_local_sdk import Configuration, DeviceType, IModel
from foundry_local_sdk.catalog import CatalogType
from openai import AsyncOpenAI, DefaultAsyncHttpxClient
from pydantic import BaseModel

from agent_framework_foundry_local._feature_usage import FeatureIndex
from agent_framework_foundry_local._foundry_local_client import FoundryLocalSettings

_OPENAI_HTTPX = cast(Any, import_module(DefaultAsyncHttpxClient.__mro__[1].__module__.partition(".")[0]))


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


@pytest.mark.parametrize("catalog_type", ["local", CatalogType.LOCAL])
@pytest.mark.parametrize("model", ["local-model", "local-model:1"])
def test_foundry_local_client_selects_local_catalog(
    mock_foundry_local_manager: MagicMock, catalog_type: Literal["local"] | CatalogType, model: str
) -> None:
    client = FoundryLocalClient(model=model, catalog_type=catalog_type)

    local_catalog = mock_foundry_local_manager.get_catalog.return_value
    mock_foundry_local_manager.get_catalog.assert_called_once_with(CatalogType.LOCAL)
    mock_foundry_local_manager.catalog.get_model.assert_not_called()
    mock_foundry_local_manager.catalog.get_model_variant.assert_not_called()
    local_catalog.get_model_variant.assert_called_with("local-model:1")
    local_catalog.get_model_variant.return_value.download.assert_called_once_with()
    local_catalog.get_model_variant.return_value.load.assert_called_once_with()
    assert client.model == "local-model:1"
    assert str(client.client.base_url) == "http://localhost:5272/catalogs/local/v1/"


@pytest.mark.parametrize("catalog_type", ["public", CatalogType.PUBLIC])
def test_foundry_local_client_selects_public_catalog(
    mock_foundry_local_manager: MagicMock, catalog_type: Literal["public"] | CatalogType
) -> None:
    client = FoundryLocalClient(model="test-model-id", catalog_type=catalog_type)
    mock_foundry_local_manager.get_catalog.assert_not_called()
    assert client.model == "test-model-id"
    assert str(client.client.base_url) == "http://localhost:5272/v1/"


@pytest.mark.parametrize("catalog_type", ["missing", None, 2])
def test_foundry_local_client_rejects_invalid_catalog_before_setup(
    mock_foundry_local_manager: MagicMock, catalog_type: Any
) -> None:
    with (
        patch("agent_framework_foundry_local._foundry_local_client.FoundryLocalManager") as manager_class,
        pytest.raises(ValueError, match="catalog_type"),
    ):
        manager_class.instance = None
        FoundryLocalClient(model="test-model-id", catalog_type=catalog_type)
    manager_class.initialize.assert_not_called()
    mock_foundry_local_manager.start_web_service.assert_not_called()


def test_foundry_local_client_local_catalog_does_not_fall_back_to_public(
    mock_foundry_local_manager: MagicMock,
) -> None:
    mock_foundry_local_manager.get_catalog.return_value.get_model_variant.return_value = None
    with pytest.raises(ValueError, match="not found"):
        FoundryLocalClient(model="test-model-id:1", catalog_type="local")
    mock_foundry_local_manager.catalog.get_model_variant.assert_not_called()
    mock_foundry_local_manager.close.assert_not_called()
    mock_foundry_local_manager.stop_web_service.assert_not_called()


def test_foundry_local_client_local_catalog_respects_manual_preparation(mock_foundry_local_manager: MagicMock) -> None:
    client = FoundryLocalClient(model="local-model:1", catalog_type="local", prepare_model=False, bootstrap=False)
    local_model = mock_foundry_local_manager.get_catalog.return_value.get_model_variant.return_value
    local_model.download.assert_not_called()
    local_model.load.assert_not_called()
    mock_foundry_local_manager.start_web_service.assert_not_called()
    assert str(client.client.base_url) == "http://localhost:5272/catalogs/local/v1/"


def test_foundry_local_client_local_catalog_selects_exact_device_variant(mock_foundry_local_manager: MagicMock) -> None:
    with pytest.raises(ValueError, match="not found"):
        FoundryLocalClient(model="local-model:1", catalog_type="local", device=DeviceType("GPU"))
    local_catalog = mock_foundry_local_manager.get_catalog.return_value
    local_catalog.get_model.assert_not_called()
    local_catalog.get_model_variant.return_value.load.assert_not_called()


def test_foundry_local_client_local_catalog_preserves_download_controls(mock_foundry_local_manager: MagicMock) -> None:
    progress: list[float] = []
    cancel_event = Event()
    FoundryLocalClient(
        model="local-model:1",
        catalog_type="local",
        download_progress_callback=progress.append,
        download_cancel_event=cancel_event,
    )
    local_model = mock_foundry_local_manager.get_catalog.return_value.get_model_variant.return_value
    local_model.download.assert_called_once_with(progress_callback=progress.append, cancel_event=cancel_event)
    local_model.load.assert_called_once_with()


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("override_model", [False, True])
async def test_foundry_local_client_local_catalog_http_route(
    mock_foundry_local_manager: MagicMock, stream: bool, override_model: bool
) -> None:
    requests: list[Any] = []

    def respond(request: Any) -> Any:
        requests.append(request)
        return _completion_response({"content": "Hello"}, stream=stream)

    async with _client_with_transport(respond, catalog_type="local", model="local-model:1") as client:
        messages = [Message(role="user", contents=["Hi"])]
        options: FoundryLocalChatOptions[None] = {"model": "other-local:2"} if override_model else {}
        if stream:
            response = await client.get_response(messages, stream=True, options=options).get_final_response()
        else:
            response = await client.get_response(messages, options=options)
    assert response.text == "Hello"
    assert requests[0].url.path == "/catalogs/local/v1/chat/completions"
    assert json.loads(requests[0].content)["model"] == ("other-local:2" if override_model else "local-model:1")


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


@pytest.mark.parametrize("first_fails", [False, True])
def test_foundry_local_client_serializes_concurrent_setup(
    mock_foundry_local_manager_factory: Callable[[], MagicMock], first_fails: bool
) -> None:
    first_manager = mock_foundry_local_manager_factory()
    first_manager.urls = None
    replacement_manager = mock_foundry_local_manager_factory()
    preparing = Event()
    release_preparation = Event()
    lock_attempts: Queue[None] = Queue()
    setup_lock = Lock()
    observed_lock = MagicMock()

    def enter_lock() -> None:
        lock_attempts.put(None)
        setup_lock.acquire()

    observed_lock.__enter__.side_effect = enter_lock
    observed_lock.__exit__.side_effect = lambda *_: setup_lock.release()

    def prepare_first_model() -> None:
        assert setup_lock.locked(), "Model preparation must remain inside the shared setup lock."
        preparing.set()
        assert release_preparation.wait(5), "Timed out waiting to release model preparation."
        if first_fails:
            raise RuntimeError("model preparation failed")

    first_manager.catalog.get_model_variant.return_value.download.side_effect = prepare_first_model
    first_manager.start_web_service.side_effect = lambda: setattr(first_manager, "urls", ["http://localhost:5272"])

    def create_client(prepare_model: bool = True) -> FoundryLocalClient[FoundryLocalChatOptions[None]]:
        return FoundryLocalClient(model="test-model-id", prepare_model=prepare_model)

    with (
        patch("agent_framework_foundry_local._foundry_local_client.FoundryLocalManager") as manager_class,
        patch("agent_framework_foundry_local._foundry_local_client._MANAGER_SETUP_LOCK", observed_lock, create=True),
        patch(
            "agent_framework_foundry_local._foundry_local_client.AsyncOpenAI", return_value=MagicMock(spec=AsyncOpenAI)
        ),
        ThreadPoolExecutor(max_workers=2) as executor,
    ):
        manager_class.instance = None
        managers = iter([first_manager, replacement_manager])
        manager_class.initialize.side_effect = lambda _: setattr(manager_class, "instance", next(managers))

        def close_first_manager() -> None:
            assert setup_lock.locked(), "Failed setup must finish cleanup before another client can use the manager."
            manager_class.instance = None

        first_manager.close.side_effect = close_first_manager
        first = executor.submit(create_client)
        try:
            assert preparing.wait(5), "First client did not reach model preparation."
            lock_attempts.get(timeout=5)
            second = executor.submit(create_client, prepare_model=False)
            lock_attempts.get(timeout=5)
            assert not second.done()
            manager_class.initialize.assert_called_once()
            first_manager.start_web_service.assert_called_once_with()
        finally:
            release_preparation.set()

        if first_fails:
            with pytest.raises(RuntimeError, match="model preparation failed"):
                first.result(timeout=5)
            assert second.result(timeout=5).manager is replacement_manager
            assert manager_class.initialize.call_count == 2
            first_manager.close.assert_called_once_with()
            replacement_manager.close.assert_not_called()
        else:
            assert first.result(timeout=5).manager is first_manager
            assert second.result(timeout=5).manager is first_manager
            manager_class.initialize.assert_called_once()
            first_manager.close.assert_not_called()
        first_manager.start_web_service.assert_called_once_with()


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


@pytest.mark.parametrize("service_running", [False, True])
@pytest.mark.parametrize("failure_stage", ["lookup", "download", "load", "http"])
@pytest.mark.parametrize("catalog_type", ["public", "local"])
def test_foundry_local_client_rolls_back_service_started_on_existing_manager(
    mock_foundry_local_manager: MagicMock,
    service_running: bool,
    failure_stage: str,
    catalog_type: Literal["public", "local"],
) -> None:
    if not service_running:
        mock_foundry_local_manager.urls = None
        mock_foundry_local_manager.start_web_service.side_effect = lambda: setattr(
            mock_foundry_local_manager, "urls", ["http://localhost:5272"]
        )
    catalog = (
        mock_foundry_local_manager.catalog
        if catalog_type == "public"
        else mock_foundry_local_manager.get_catalog.return_value
    )
    model = catalog.get_model_variant.return_value
    if failure_stage == "lookup":
        catalog.get_model.return_value = None
    elif failure_stage in ("download", "load"):
        getattr(model, failure_stage).side_effect = RuntimeError("setup failed")
    with (
        patch("agent_framework_foundry_local._foundry_local_client.AsyncOpenAI") as http_client,
        pytest.raises(ValueError if failure_stage == "lookup" else RuntimeError),
    ):
        if failure_stage == "http":
            http_client.side_effect = RuntimeError("setup failed")
        FoundryLocalClient(model="test-model-id", catalog_type=catalog_type)
    mock_foundry_local_manager.close.assert_not_called()
    if service_running:
        mock_foundry_local_manager.stop_web_service.assert_not_called()
    else:
        mock_foundry_local_manager.start_web_service.assert_called_once_with()
        mock_foundry_local_manager.stop_web_service.assert_called_once_with()


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


def test_foundry_local_client_passes_download_controls(mock_foundry_local_manager: MagicMock) -> None:
    progress = MagicMock()
    cancel_event = Event()
    FoundryLocalClient(model="test-model-id", download_progress_callback=progress, download_cancel_event=cancel_event)
    mock_model = mock_foundry_local_manager.catalog.get_model_variant.return_value
    mock_model.download.assert_called_once_with(progress_callback=progress, cancel_event=cancel_event)
    mock_model.load.assert_called_once_with()


def test_foundry_local_client_cancelled_download_does_not_load(mock_foundry_local_manager: MagicMock) -> None:
    cancel_event = Event()
    cancel_event.set()
    mock_model = mock_foundry_local_manager.catalog.get_model_variant.return_value
    mock_model.download.side_effect = RuntimeError("download cancelled")

    with pytest.raises(RuntimeError, match="download cancelled"):
        FoundryLocalClient(model="test-model-id", download_cancel_event=cancel_event)

    mock_model.download.assert_called_once_with(progress_callback=None, cancel_event=cancel_event)
    mock_model.load.assert_not_called()
    mock_foundry_local_manager.close.assert_not_called()


def test_foundry_local_client_skips_download_controls_without_preparation(
    mock_foundry_local_manager: MagicMock,
) -> None:
    FoundryLocalClient(
        model="test-model-id",
        prepare_model=False,
        download_progress_callback=MagicMock(),
        download_cancel_event=Event(),
    )
    mock_model = mock_foundry_local_manager.catalog.get_model_variant.return_value
    mock_model.download.assert_not_called()
    mock_model.load.assert_not_called()


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
        FoundryLocalClient(model="exact-variant:1", device=DeviceType("GPU"))
    mock_foundry_local_manager.catalog.get_model.return_value.download.assert_not_called()


def test_foundry_local_client_missing_device_variant(mock_foundry_local_manager: MagicMock) -> None:
    with pytest.raises(ValueError, match="model-alias:GPU.*not found"):
        FoundryLocalClient(model="model-alias", device=DeviceType("GPU"))


def test_foundry_local_client_unknown_runtime_does_not_match_device(mock_foundry_local_manager: MagicMock) -> None:
    mock_model = mock_foundry_local_manager.catalog.get_model_variant.return_value
    mock_model.info.runtime = None
    with pytest.raises(ValueError, match="model-alias:CPU.*not found"):
        FoundryLocalClient(model="model-alias", device=DeviceType("CPU"))


def test_foundry_local_client_invalid_device(mock_foundry_local_manager: MagicMock) -> None:
    with pytest.raises(ValueError, match="DeviceType"):
        FoundryLocalClient(model="model-alias", device=cast(DeviceType, "invalid"))
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
    requests: list[Any] = []

    def respond(request: Any) -> Any:
        requests.append(request)
        completion = {
            "id": "completion-1",
            "created": 0,
            "model": "test-model-id",
            "object": "chat.completion",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hello"}, "finish_reason": "stop"}],
        }
        if not stream:
            return _OPENAI_HTTPX.Response(200, json=completion)
        completion["object"] = "chat.completion.chunk"
        completion["choices"] = [
            {"index": 0, "delta": {"role": "assistant", "content": "Hello"}, "finish_reason": "stop"}
        ]
        return _OPENAI_HTTPX.Response(
            200,
            headers={"content-type": "text/event-stream"},
            text=f"data: {json.dumps(completion)}\n\ndata: [DONE]\n\n",
        )

    async with DefaultAsyncHttpxClient(transport=_OPENAI_HTTPX.MockTransport(respond)) as http_client:
        async_client = AsyncOpenAI(
            base_url="http://localhost:5272/v1", api_key="foundry-local", http_client=http_client
        )
        with patch("agent_framework_foundry_local._foundry_local_client.AsyncOpenAI", return_value=async_client):
            client = FoundryLocalClient(model="test-model-id", prepare_model=False)
        messages = [Message(role="user", contents=["Hi"])]
        if stream:
            result = "".join([update.text async for update in client.get_response(messages, stream=True)])
        else:
            result = (await client.get_response(messages)).text

    assert result == "Hello"
    assert len(requests) == 1
    assert requests[0].url.path == "/v1/chat/completions"
    payload = json.loads(requests[0].content)
    assert payload["model"] == "test-model-id"
    assert payload["stream"] is stream


@asynccontextmanager
async def _client_with_transport(
    respond: Callable[[Any], Any],
    *,
    middleware: Sequence[ChatAndFunctionMiddlewareTypes] | None = None,
    function_invocation_configuration: FunctionInvocationConfiguration | None = None,
    catalog_type: Literal["public", "local"] = "public",
    model: str = "test-model-id",
    prepare_model: bool = False,
    device: DeviceType | Literal["CPU", "GPU", "NPU"] | None = None,
    download_progress_callback: Callable[[float], None] | None = None,
    download_cancel_event: Event | None = None,
) -> AsyncGenerator[FoundryLocalClient[FoundryLocalChatOptions[None]]]:
    async with (
        DefaultAsyncHttpxClient(transport=_OPENAI_HTTPX.MockTransport(respond), trust_env=False) as http_client,
        AsyncOpenAI(
            base_url=f"http://localhost:5272{'/catalogs/local' if catalog_type == 'local' else ''}/v1",
            api_key="foundry-local",
            http_client=http_client,
            max_retries=0,
        ) as async_client,
    ):
        with patch("agent_framework_foundry_local._foundry_local_client.AsyncOpenAI", return_value=async_client):
            yield FoundryLocalClient(
                model=model,
                catalog_type=catalog_type,
                prepare_model=prepare_model,
                device=device,
                download_progress_callback=download_progress_callback,
                download_cancel_event=download_cancel_event,
                middleware=middleware,
                function_invocation_configuration=function_invocation_configuration,
            )


def _completion_response(message: dict[str, Any], *, stream: bool, finish_reason: str = "stop") -> Any:
    usage = {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8}
    message = {"role": "assistant", **message}
    if not stream:
        return _OPENAI_HTTPX.Response(
            200,
            json={
                "id": "completion-1",
                "created": 0,
                "model": "test-model-id",
                "object": "chat.completion",
                "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
                "usage": usage,
            },
        )
    if "tool_calls" in message:
        message["tool_calls"] = [{"index": index, **call} for index, call in enumerate(message["tool_calls"])]
    chunk = {
        "id": "completion-1",
        "created": 0,
        "model": "test-model-id",
        "object": "chat.completion.chunk",
        "choices": [{"index": 0, "delta": message, "finish_reason": finish_reason}],
        "usage": usage,
    }
    return _OPENAI_HTTPX.Response(
        200,
        headers={"content-type": "text/event-stream"},
        text=f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n",
    )


@pytest.mark.parametrize("stream", [False, True])
async def test_foundry_local_eager_preparation_still_prepares_during_construction(
    mock_foundry_local_manager: MagicMock, stream: bool
) -> None:
    model = mock_foundry_local_manager.catalog.get_model_variant.return_value

    def respond(request: Any) -> Any:
        model.download.assert_called_once_with()
        model.load.assert_called_once_with()
        return _completion_response({"content": "Hello"}, stream=stream)

    async with _client_with_transport(respond, prepare_model=True) as client:
        model.download.assert_called_once_with()
        model.load.assert_called_once_with()
        messages = [Message(role="user", contents=["Hi"])]
        if stream:
            response = await client.get_response(messages, stream=True).get_final_response()
        else:
            response = await client.get_response(messages)
        assert response.text == "Hello"


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("catalog_type", ["public", "local"])
async def test_foundry_local_lazy_preparation_pins_variant_and_preserves_download_controls(
    mock_foundry_local_manager: MagicMock, stream: bool, catalog_type: Literal["public", "local"]
) -> None:
    catalog = (
        mock_foundry_local_manager.catalog
        if catalog_type == "public"
        else mock_foundry_local_manager.get_catalog.return_value
    )
    variant = MagicMock(spec=IModel)
    variant.id = "selected-gpu:2"
    variant.info = SimpleNamespace(runtime=SimpleNamespace(device_type=DeviceType.GPU))
    variant.is_loaded = False
    catalog.get_model.return_value.variants.append(variant)
    event_loop_thread = get_ident()
    progress_threads: list[int] = []
    progress: list[float] = []
    cancel_event = Event()
    payloads: list[dict[str, Any]] = []

    def report_progress(value: float) -> None:
        progress_threads.append(get_ident())
        progress.append(value)

    def download(*, progress_callback: Callable[[float], None], cancel_event: Event) -> None:
        assert not cancel_event.is_set()
        assert get_ident() != event_loop_thread
        progress_callback(100.0)

    def load() -> None:
        assert get_ident() != event_loop_thread
        variant.is_loaded = True

    variant.download.side_effect = download
    variant.load.side_effect = load

    def respond(request: Any) -> Any:
        assert variant.is_loaded
        payloads.append(json.loads(request.content))
        return _completion_response({"content": "Hello"}, stream=stream)

    async with _client_with_transport(
        respond,
        model="model-alias",
        catalog_type=catalog_type,
        device="GPU",
        download_progress_callback=report_progress,
        download_cancel_event=cancel_event,
    ) as client:
        variant.download.assert_not_called()
        variant.load.assert_not_called()
        for _ in range(2):
            messages = [Message(role="user", contents=["Hi"])]
            if stream:
                response_stream = client.get_response(messages, stream=True)
                if not payloads:
                    variant.load.assert_not_called()
                response = await response_stream.get_final_response()
            else:
                response = await client.get_response(messages)
            assert response.text == "Hello"
    assert [payload["model"] for payload in payloads] == ["selected-gpu:2", "selected-gpu:2"]
    variant.download.assert_called_once_with(progress_callback=report_progress, cancel_event=cancel_event)
    variant.load.assert_called_once_with()
    catalog.get_model.return_value.select_variant.assert_not_called()
    assert progress == [100.0]
    assert progress_threads[0] != event_loop_thread


@pytest.mark.parametrize("stream", [False, True])
async def test_foundry_local_lazy_preparation_reuses_loaded_model(
    mock_foundry_local_manager: MagicMock, stream: bool
) -> None:
    model = mock_foundry_local_manager.catalog.get_model_variant.return_value

    def respond(request: Any) -> Any:
        return _completion_response({"content": "Hello"}, stream=stream)

    async with _client_with_transport(respond) as client:
        # Manual preparation after client construction must also be respected.
        model.is_loaded = True
        messages = [Message(role="user", contents=["Hi"])]
        if stream:
            response = await client.get_response(messages, stream=True).get_final_response()
        else:
            response = await client.get_response(messages)
        assert response.text == "Hello"
    model.download.assert_not_called()
    model.load.assert_not_called()


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("stage", ["download", "load"])
async def test_foundry_local_lazy_preparation_failure_does_not_send_inference_and_can_retry(
    mock_foundry_local_manager: MagicMock, stream: bool, stage: str
) -> None:
    model = mock_foundry_local_manager.catalog.get_model_variant.return_value
    failed_operation = model.download if stage == "download" else model.load
    failed_operation.side_effect = RuntimeError(f"{stage} failed")
    requests: list[Any] = []

    def respond(request: Any) -> Any:
        requests.append(request)
        assert model.is_loaded
        return _completion_response({"content": "Hello"}, stream=stream)

    async with _client_with_transport(respond) as client:
        messages = [Message(role="user", contents=["Hi"])]
        with pytest.raises(RuntimeError, match=f"{stage} failed"):
            if stream:
                await client.get_response(messages, stream=True).get_final_response()
            else:
                await client.get_response(messages)
        assert not requests
        if stage == "download":
            model.load.assert_not_called()
        failed_operation.side_effect = None if stage == "download" else lambda: setattr(model, "is_loaded", True)
        if stream:
            response = await client.get_response(messages, stream=True).get_final_response()
        else:
            response = await client.get_response(messages)
        assert response.text == "Hello"
    assert len(requests) == 1
    mock_foundry_local_manager.close.assert_not_called()
    mock_foundry_local_manager.stop_web_service.assert_not_called()


@pytest.mark.parametrize("stream", [False, True])
async def test_foundry_local_lazy_preparation_serializes_clients_without_blocking_event_loop(
    mock_foundry_local_manager: MagicMock, stream: bool
) -> None:
    model = mock_foundry_local_manager.catalog.get_model_variant.return_value
    started = Event()
    release = Event()
    requests: list[Any] = []

    def load() -> None:
        started.set()
        if not release.wait(timeout=5):
            raise TimeoutError("Test did not release native loading.")
        model.is_loaded = True

    model.load.side_effect = load

    def respond(request: Any) -> Any:
        assert model.is_loaded
        requests.append(request)
        return _completion_response({"content": "Hello"}, stream=stream)

    async with _client_with_transport(respond) as first, _client_with_transport(respond) as second:

        async def request_response(client: FoundryLocalClient[FoundryLocalChatOptions[None]]) -> str:
            messages = [Message(role="user", contents=["Hi"])]
            if stream:
                return (await client.get_response(messages, stream=True).get_final_response()).text
            return (await client.get_response(messages)).text

        first_request = asyncio.create_task(request_response(first))
        second_request = asyncio.create_task(request_response(second))
        try:
            assert await asyncio.to_thread(started.wait, 5)
            await asyncio.sleep(0)
            assert not first_request.done()
            assert not second_request.done()
            assert not requests
        finally:
            release.set()
        assert await asyncio.gather(first_request, second_request) == ["Hello", "Hello"]
    model.download.assert_called_once_with()
    model.load.assert_called_once_with()
    assert len(requests) == 2


@pytest.mark.parametrize("stream", [False, True])
async def test_foundry_local_cancelling_lazy_request_preserves_native_preparation(
    mock_foundry_local_manager: MagicMock, stream: bool
) -> None:
    model = mock_foundry_local_manager.catalog.get_model_variant.return_value
    started = Event()
    release = Event()
    requests: list[Any] = []

    def load() -> None:
        started.set()
        if not release.wait(timeout=5):
            raise TimeoutError("Test did not release native loading.")
        model.is_loaded = True

    model.load.side_effect = load

    def respond(request: Any) -> Any:
        assert model.is_loaded
        requests.append(request)
        return _completion_response({"content": "Hello"}, stream=stream)

    async with _client_with_transport(respond) as client:

        async def request_response() -> str:
            messages = [Message(role="user", contents=["Hi"])]
            if stream:
                return (await client.get_response(messages, stream=True).get_final_response()).text
            return (await client.get_response(messages)).text

        first_request = asyncio.create_task(request_response())
        try:
            assert await asyncio.to_thread(started.wait, 5)
            first_request.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first_request
            assert not requests
            assert not model.is_loaded
        finally:
            release.set()
        assert await request_response() == "Hello"
    assert len(requests) == 1
    model.download.assert_called_once_with()
    model.load.assert_called_once_with()
    mock_foundry_local_manager.close.assert_not_called()
    mock_foundry_local_manager.stop_web_service.assert_not_called()


@pytest.mark.parametrize("stream", [False, True])
async def test_foundry_local_deferred_download_honors_cancellation_event(
    mock_foundry_local_manager: MagicMock, stream: bool
) -> None:
    model = mock_foundry_local_manager.catalog.get_model_variant.return_value
    cancel_event = Event()
    cancel_event.set()
    requests: list[Any] = []

    def download(*, progress_callback: Callable[[float], None] | None, cancel_event: Event) -> None:
        assert cancel_event.is_set()
        raise RuntimeError("download cancelled")

    model.download.side_effect = download

    def respond(request: Any) -> Any:
        requests.append(request)
        return _completion_response({"content": "Hello"}, stream=stream)

    async with _client_with_transport(respond, download_cancel_event=cancel_event) as client:
        model.download.assert_not_called()
        with pytest.raises(RuntimeError, match="download cancelled"):
            messages = [Message(role="user", contents=["Hi"])]
            if stream:
                await client.get_response(messages, stream=True).get_final_response()
            else:
                await client.get_response(messages)
    model.download.assert_called_once_with(progress_callback=None, cancel_event=cancel_event)
    model.load.assert_not_called()
    assert not requests


@pytest.mark.parametrize("stream", [False, True])
async def test_foundry_local_lazy_preparation_does_not_provision_request_overrides(
    mock_foundry_local_manager: MagicMock, stream: bool
) -> None:
    model = mock_foundry_local_manager.catalog.get_model_variant.return_value
    payloads: list[dict[str, Any]] = []

    def respond(request: Any) -> Any:
        payloads.append(json.loads(request.content))
        return _completion_response({"content": "Hello"}, stream=stream)

    async with _client_with_transport(respond) as client:
        messages = [Message(role="user", contents=["Hi"])]
        if stream:
            response = await client.get_response(
                messages, stream=True, options={"model": "caller-prepared:1"}
            ).get_final_response()
        else:
            response = await client.get_response(messages, options={"model": "caller-prepared:1"})
        assert response.text == "Hello"
    assert payloads[0]["model"] == "caller-prepared:1"
    model.download.assert_not_called()
    model.load.assert_not_called()


@pytest.mark.parametrize("stream", [False, True])
async def test_foundry_local_generation_options_and_usage(mock_foundry_local_manager: MagicMock, stream: bool) -> None:
    requests: list[Any] = []

    def respond(request: Any) -> Any:
        requests.append(request)
        return _completion_response({"content": "Hello"}, stream=stream)

    options: FoundryLocalChatOptions[None] = {
        "temperature": 0.0,
        "top_p": 0.8,
        "max_tokens": 32,
        "seed": 0,
        "top_k": 0,
        "do_sample": False,
        "early_stopping": False,
        "frequency_penalty": 0.0,
        "presence_penalty": 0.0,
        "stop": ["END"],
        "logit_bias": {"42": -1.0},
        "instructions": "Be concise.",
        "metadata": {"top_k": "16", "native_custom": "keep"},
        "extra_body": {"metadata": {"top_k": "8"}, "custom_setting": "test"},
    }
    original_options = json.loads(json.dumps(options))
    async with _client_with_transport(respond) as client:
        messages = [Message(role="user", contents=["Hi"])]
        if stream:
            response_stream = client.get_response(
                messages, stream=True, options=options, client_kwargs={"extra_headers": {"X-Test-Header": "present"}}
            )
            response = await response_stream.get_final_response()
        else:
            response = await client.get_response(
                messages, options=options, client_kwargs={"extra_headers": {"X-Test-Header": "present"}}
            )

    assert response.text == "Hello"
    assert response.usage_details is not None
    assert response.usage_details["input_token_count"] == 5
    assert response.usage_details["output_token_count"] == 3
    assert requests[0].headers["X-Test-Header"] == "present"
    payload = json.loads(requests[0].content)
    for key in (
        "temperature",
        "top_p",
        "max_tokens",
        "seed",
        "frequency_penalty",
        "presence_penalty",
        "stop",
        "logit_bias",
    ):
        assert payload[key] == original_options[key]
    assert payload["messages"][0] == {"role": "system", "content": "Be concise."}
    assert payload["metadata"] == {
        "top_k": "0",
        "do_sample": "false",
        "early_stopping": "false",
        "native_custom": "keep",
    }
    assert all(key not in payload for key in ("top_k", "do_sample", "early_stopping", "max_completion_tokens"))
    assert payload["custom_setting"] == "test"
    assert options == original_options
    if stream:
        assert payload["stream_options"] == {"include_usage": True}
    mock_foundry_local_manager.close.assert_not_called()


@pytest.mark.parametrize("stream", [False, True])
async def test_foundry_local_decoder_metadata_passthrough(mock_foundry_local_manager: MagicMock, stream: bool) -> None:
    payloads: list[dict[str, Any]] = []

    def respond(request: Any) -> Any:
        payloads.append(json.loads(request.content))
        return _completion_response({"content": "Hello"}, stream=stream)

    options: FoundryLocalChatOptions[None] = {
        "metadata": {"do_sample": "false"},
        "extra_body": {"metadata": {"top_k": "8"}},
    }
    original_options = deepcopy(options)
    async with _client_with_transport(respond) as client:
        messages = [Message(role="user", contents=["Hi"])]
        if stream:
            await client.get_response(messages, stream=True, options=options).get_final_response()
        else:
            await client.get_response(messages, options=options)
    assert payloads[0]["metadata"] == {"top_k": "8", "do_sample": "false"}
    assert options == original_options


@pytest.mark.parametrize("stream", [False, True])
async def test_foundry_local_request_model_override(mock_foundry_local_manager: MagicMock, stream: bool) -> None:
    payloads: list[dict[str, Any]] = []

    def respond(request: Any) -> Any:
        payloads.append(json.loads(request.content))
        return _completion_response({"content": "Hello"}, stream=stream)

    async with _client_with_transport(respond) as client:
        messages = [Message(role="user", contents=["Hi"])]
        if stream:
            await client.get_response(messages, stream=True, options={"model": "other-variant:1"}).get_final_response()
        else:
            await client.get_response(messages, options={"model": "other-variant:1"})
        assert client.model == "test-model-id"
    assert payloads[0]["model"] == "other-variant:1"


@pytest.mark.parametrize("invalid_metadata", [0, "invalid", ["top_k", "8"]])
async def test_foundry_local_invalid_decoder_metadata(
    mock_foundry_local_manager: MagicMock, invalid_metadata: object
) -> None:
    requests: list[Any] = []

    def respond(request: Any) -> Any:
        requests.append(request)
        return _completion_response({"content": "Hello"}, stream=False)

    options: FoundryLocalChatOptions[None] = {
        "top_k": 1,
        "metadata": cast(dict[str, Any], invalid_metadata),
    }
    async with _client_with_transport(respond) as client:
        with pytest.raises(ValueError, match="metadata must be a mapping"):
            await client.get_response([Message(role="user", contents=["Hi"])], options=options)
    assert not requests


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "object", "properties": {"answer": {"type": "integer"}}},
        {"properties": {"answer": {"type": "integer"}}},
        {"$defs": {"Answer": {"type": "integer"}}, "$ref": "#/$defs/Answer"},
    ],
)
def test_foundry_local_raw_schema_from_older_openai_adapter(
    mock_foundry_local_manager: MagicMock, schema: dict[str, Any]
) -> None:
    client = FoundryLocalClient(model="test-model-id")
    original_schema = deepcopy(schema)
    # agent-framework-openai 1.6.0 passes raw schema dictionaries through unchanged.
    with patch.object(RawOpenAIChatCompletionClient, "_prepare_options", return_value={"response_format": schema}):
        prepared = client._prepare_options([], {"response_format": schema})
    assert prepared["response_format"] == {"type": "json_schema", "json_schema": schema}
    assert schema == original_schema


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize(
    "format_kind",
    ["pydantic", "schema", "schema_no_type", "schema_ref", "native_schema", "named_schema", "json_object"],
)
async def test_foundry_local_structured_responses(
    mock_foundry_local_manager: MagicMock, stream: bool, format_kind: str
) -> None:
    class Answer(BaseModel):
        answer: int

    payloads: list[dict[str, Any]] = []

    def respond(request: Any) -> Any:
        payloads.append(json.loads(request.content))
        return _completion_response({"content": '{"answer": 4}'}, stream=stream)

    schema: dict[str, Any] = {
        "type": "object",
        "properties": {"answer": {"type": "integer"}},
        "required": ["answer"],
    }
    if format_kind == "schema_no_type":
        schema.pop("type")
    elif format_kind == "schema_ref":
        schema = {"$defs": {"Answer": schema}, "$ref": "#/$defs/Answer"}
    options: FoundryLocalChatOptions[Answer] = {
        "response_format": Answer
        if format_kind == "pydantic"
        else schema
        if format_kind in ("schema", "schema_no_type", "schema_ref")
        else {"type": "json_schema", "json_schema": schema}
        if format_kind == "native_schema"
        else {"type": "json_schema", "json_schema": {"name": "Answer", "schema": schema, "strict": True}}
        if format_kind == "named_schema"
        else {"type": "json_object"}
    }
    original_options = deepcopy(options)
    async with _client_with_transport(respond) as client:
        messages = [Message(role="user", contents=["What is 2+2?"])]
        if stream:
            response = await client.get_response(messages, stream=True, options=options).get_final_response()
        else:
            response = await client.get_response(messages, options=options)
    if format_kind == "pydantic":
        assert isinstance(response.value, Answer)
        assert response.value.answer == 4
    else:
        assert response.value == {"answer": 4}
    assert payloads[0]["response_format"]["type"] == ("json_object" if format_kind == "json_object" else "json_schema")
    if format_kind != "json_object":
        native_schema = payloads[0]["response_format"]["json_schema"]
        assert isinstance(native_schema, dict)
        if format_kind == "schema_ref":
            assert native_schema["$ref"] == "#/$defs/Answer"
            native_schema = native_schema["$defs"]["Answer"]
        if format_kind != "schema_no_type":
            assert native_schema["type"] == "object"
        assert native_schema["properties"]["answer"]["type"] == "integer"
    assert options == original_options


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("enabled", [False, True])
async def test_foundry_local_agent_tool_loop(
    mock_foundry_local_manager: MagicMock, stream: bool, enabled: bool
) -> None:
    payloads: list[dict[str, Any]] = []
    invocations: list[tuple[int, int]] = []

    @tool
    def add(a: int, b: int) -> int:
        """Add two integers."""
        invocations.append((a, b))
        return a + b

    def respond(request: Any) -> Any:
        payloads.append(json.loads(request.content))
        if len(payloads) == 1:
            return _completion_response(
                {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-add",
                            "type": "function",
                            "function": {"name": "add", "arguments": '{"a":2,"b":3}'},
                        }
                    ],
                },
                stream=stream,
                finish_reason="tool_calls",
            )
        return _completion_response({"content": "5"}, stream=stream)

    async with _client_with_transport(respond, function_invocation_configuration={"enabled": enabled}) as client:
        agent = Agent(client=client, tools=add, instructions="Use the calculator.")
        if stream:
            response = await agent.run(
                "What is 2+3?", stream=True, options={"tool_choice": "required", "allow_multiple_tool_calls": False}
            ).get_final_response()
        else:
            response = await agent.run(
                "What is 2+3?", options={"tool_choice": "required", "allow_multiple_tool_calls": False}
            )

    assert payloads[0]["tools"][0]["function"]["name"] == "add"
    assert payloads[0]["tool_choice"] == "required"
    assert payloads[0]["parallel_tool_calls"] is False
    if enabled:
        assert invocations == [(2, 3)]
        assert len(payloads) == 2
        assert response.text == "5"
        tool_messages = [message for message in payloads[1]["messages"] if message["role"] == "tool"]
        assert len(tool_messages) == 1
        assert tool_messages[0]["tool_call_id"] == "call-add"
        assert tool_messages[0]["content"] == "5"
    else:
        assert invocations == []
        assert len(payloads) == 1
        assert any(content.type == "function_call" for message in response.messages for content in message.contents)


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("named_tool", [False, True])
@pytest.mark.parametrize("json_object", [False, True])
async def test_foundry_local_required_tools_with_structured_output(
    mock_foundry_local_manager: MagicMock, stream: bool, named_tool: bool, json_object: bool
) -> None:
    class Answer(BaseModel):
        answer: int

    payloads: list[dict[str, Any]] = []
    invocations: list[tuple[int, int]] = []

    @tool
    def add(a: int, b: int) -> int:
        """Add two integers."""
        invocations.append((a, b))
        return a + b

    def respond(request: Any) -> Any:
        payload = json.loads(request.content)
        payloads.append(payload)
        if len(payloads) == 1:
            assert "response_format" not in payload
            assert payload["tool_choice"] == (
                {"type": "function", "function": {"name": "add"}} if named_tool else "required"
            )
            return _completion_response(
                {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-add",
                            "type": "function",
                            "function": {"name": "add", "arguments": '{"a":2,"b":3}'},
                        }
                    ],
                },
                stream=stream,
                finish_reason="tool_calls",
            )
        assert payload["response_format"]["type"] == ("json_object" if json_object else "json_schema")
        if not json_object:
            assert payload["response_format"]["json_schema"]["properties"]["answer"]["type"] == "integer"
        return _completion_response({"content": '{"answer":5}'}, stream=stream)

    options: ChatOptions[Answer] = {
        "tool_choice": {"mode": "required", "required_function_name": "add"} if named_tool else "required",
        "response_format": {"type": "json_object"} if json_object else Answer,
    }
    original_options = deepcopy(options)
    async with _client_with_transport(respond) as client:
        agent = Agent(client=client, tools=add)
        if stream:
            response = await agent.run("What is 2+3?", stream=True, options=options).get_final_response()
        else:
            response = await agent.run("What is 2+3?", options=options)
    assert invocations == [(2, 3)]
    assert len(payloads) == 2
    if json_object:
        assert response.value == {"answer": 5}
    else:
        assert isinstance(response.value, Answer)
        assert response.value.answer == 5
    assert options == original_options


@pytest.mark.parametrize("stream", [False, True])
async def test_foundry_local_constructor_and_per_call_middleware(
    mock_foundry_local_manager: MagicMock, stream: bool
) -> None:
    order: list[str] = []
    payloads: list[dict[str, Any]] = []

    @chat_middleware
    async def constructor_middleware(context: ChatContext, call_next: Callable[[], Awaitable[None]]) -> None:
        order.append("constructor-before")
        context.options = {**(context.options or {}), "temperature": 0.1}
        await call_next()
        order.append("constructor-after")

    @chat_middleware
    async def per_call_middleware(context: ChatContext, call_next: Callable[[], Awaitable[None]]) -> None:
        order.append("per-call-before")
        context.options = {**(context.options or {}), "top_p": 0.5}
        await call_next()
        order.append("per-call-after")

    def respond(request: Any) -> Any:
        payloads.append(json.loads(request.content))
        return _completion_response({"content": "Hello"}, stream=stream)

    async with _client_with_transport(respond, middleware=[constructor_middleware]) as client:
        messages = [Message(role="user", contents=["Hi"])]
        if stream:
            response = await client.get_response(
                messages, stream=True, middleware=[per_call_middleware]
            ).get_final_response()
        else:
            response = await client.get_response(messages, middleware=[per_call_middleware])
    assert response.text == "Hello"
    assert order == ["constructor-before", "per-call-before", "per-call-after", "constructor-after"]
    assert payloads[0]["temperature"] == 0.1
    assert payloads[0]["top_p"] == 0.5


@pytest.mark.parametrize("stream", [False, True])
async def test_foundry_local_agent_session_preserves_history(
    mock_foundry_local_manager: MagicMock, stream: bool
) -> None:
    payloads: list[dict[str, Any]] = []

    def respond(request: Any) -> Any:
        payloads.append(json.loads(request.content))
        return _completion_response({"content": "Remembered" if len(payloads) == 1 else "LANTERN"}, stream=stream)

    async with _client_with_transport(respond) as client:
        agent = Agent(client=client, instructions="Remember the conversation.")
        session = agent.create_session()
        if stream:
            await agent.run("Remember LANTERN", session=session, stream=True).get_final_response()
            response = await agent.run("What did I say?", session=session, stream=True).get_final_response()
        else:
            await agent.run("Remember LANTERN", session=session)
            response = await agent.run("What did I say?", session=session)
    assert response.text == "LANTERN"
    assert [message["role"] for message in payloads[1]["messages"]] == ["system", "user", "assistant", "user"]
    assert payloads[1]["messages"][1]["content"] == "Remember LANTERN"
    assert payloads[1]["messages"][2]["content"] == "Remembered"


@pytest.mark.parametrize("stream", [False, True])
async def test_foundry_local_multimodal_request_serialization(
    mock_foundry_local_manager: MagicMock, stream: bool
) -> None:
    payloads: list[dict[str, Any]] = []

    def respond(request: Any) -> Any:
        payloads.append(json.loads(request.content))
        return _completion_response({"content": "A red square"}, stream=stream)

    async with _client_with_transport(respond) as client:
        messages = [
            Message(
                role="user",
                contents=[
                    "Describe this image",
                    Content.from_uri("https://example.test/image.png", media_type="image/png"),
                ],
            )
        ]
        if stream:
            response = await client.get_response(messages, stream=True).get_final_response()
        else:
            response = await client.get_response(messages)
    assert response.text == "A red square"
    assert payloads[0]["messages"] == [
        {"role": "user", "content": "Describe this image"},
        {
            "role": "user",
            "content": [{"type": "image_url", "image_url": {"url": "https://example.test/image.png"}}],
        },
    ]


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("status", [400, 404, 429, 503])
async def test_foundry_local_http_errors_remain_visible(
    mock_foundry_local_manager: MagicMock, stream: bool, status: int
) -> None:
    def respond(request: Any) -> Any:
        return _OPENAI_HTTPX.Response(
            status, json={"error": {"message": "native inference failed", "type": "server_error"}}
        )

    async with _client_with_transport(respond) as client:
        with pytest.raises(ChatClientException, match="native inference failed"):
            messages = [Message(role="user", contents=["Hi"])]
            if stream:
                await client.get_response(messages, stream=True).get_final_response()
            else:
                await client.get_response(messages)
    mock_foundry_local_manager.close.assert_not_called()


async def test_foundry_local_request_cancellation_preserves_manager(mock_foundry_local_manager: MagicMock) -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    requests = 0

    async def respond(request: Any) -> Any:
        nonlocal requests
        requests += 1
        if requests == 1:
            started.set()
            await release.wait()
        return _completion_response({"content": "Hello"}, stream=False)

    async with _client_with_transport(respond) as client:
        messages = [Message(role="user", contents=["Hi"])]

        async def request_response() -> None:
            await client.get_response(messages)

        task = asyncio.create_task(request_response())
        try:
            await asyncio.wait_for(started.wait(), timeout=5)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            response = await client.get_response(messages)
            assert response.text == "Hello"
        finally:
            release.set()
            task.cancel()
    mock_foundry_local_manager.close.assert_not_called()
