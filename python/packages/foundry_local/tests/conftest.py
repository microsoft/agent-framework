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
        "FOUNDRY_LOCAL_MODEL_ID": "test-model-id",
    }

    env_vars.update(override_env_param_dict)

    for key, value in env_vars.items():
        if key in exclude_list:
            monkeypatch.delenv(key, raising=False)
            continue
        monkeypatch.setenv(key, value)

    return env_vars


@fixture
def mock_foundry_local_manager() -> MagicMock:
    """Fixture that provides a mock FoundryLocalManager."""
    mock_manager = MagicMock()
    mock_manager.endpoint = "http://localhost:5272/v1"
    mock_manager.api_key = "test-api-key"

    mock_model_info = MagicMock()
    mock_model_info.id = "test-model-id"
    mock_manager.get_model_info.return_value = mock_model_info

    return mock_manager
