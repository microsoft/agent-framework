# Copyright (c) Microsoft. All rights reserved.
from typing import Any
from unittest.mock import MagicMock

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
def mock_foundry_local_model() -> MagicMock:
    """Fixture that provides a mock catalog model."""
    mock_model = MagicMock()
    mock_model.id = "test-model-id"
    mock_model.alias = "test-model"
    mock_model.variants = []

    return mock_model


@fixture
def mock_foundry_local_manager(mock_foundry_local_model: MagicMock) -> MagicMock:
    """Fixture that provides a mock FoundryLocalManager."""
    mock_manager = MagicMock()
    # ``urls`` is populated by ``start_web_service()``; model a service that is already up.
    mock_manager.urls = ["http://localhost:5272"]
    mock_manager.catalog.get_model.return_value = mock_foundry_local_model
    # An alias lookup is the primary path; leave the model-ID fallback empty by default.
    mock_manager.catalog.get_model_variant.return_value = None

    return mock_manager
