# Copyright (c) Microsoft. All rights reserved.
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

from foundry_local_sdk import Catalog, DeviceType, FoundryLocalManager, IModel
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
def foundry_local_unit_test_env(monkeypatch: Any, exclude_list: list[str], override_env_param_dict: dict[str, str]):
    """Fixture to set environment variables for FoundryLocalSettings."""
    if exclude_list is None:
        exclude_list = []

    if override_env_param_dict is None:
        override_env_param_dict = {}

    env_vars = {
        "FOUNDRY_LOCAL_MODEL": "test-model-id",
    }

    env_vars.update(override_env_param_dict)

    for key, value in env_vars.items():
        if key in exclude_list:
            monkeypatch.delenv(key, raising=False)
            continue
        monkeypatch.setenv(key, value)

    return env_vars


@fixture
def mock_foundry_local_manager() -> Iterator[MagicMock]:
    """Fixture that provides a mock FoundryLocalManager."""
    mock_manager = MagicMock(spec=FoundryLocalManager)
    mock_manager.urls = ["http://localhost:5272"]
    mock_manager.catalog = MagicMock(spec=Catalog)

    mock_model = MagicMock(spec=IModel)
    mock_model.id = "test-model-id"
    mock_model.info = SimpleNamespace(runtime=SimpleNamespace(device_type=DeviceType.CPU))
    mock_model.variants = [mock_model]
    mock_manager.catalog.get_model.return_value = mock_model
    mock_manager.catalog.get_model_variant.return_value = mock_model

    with patch("agent_framework_foundry_local._foundry_local_client.FoundryLocalManager") as manager_class:
        manager_class.instance = mock_manager
        yield mock_manager
