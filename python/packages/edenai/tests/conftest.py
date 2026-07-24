# Copyright (c) Microsoft. All rights reserved.
from typing import Any

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
def edenai_unit_test_env(monkeypatch: Any, exclude_list: list[str], override_env_param_dict: dict[str, str]):
    """Fixture to set environment variables for EdenAISettings."""
    if exclude_list is None:
        exclude_list = []

    if override_env_param_dict is None:
        override_env_param_dict = {}

    env_vars = {
        "EDENAI_API_KEY": "test-api-key",
        "EDENAI_MODEL": "openai/gpt-4o-mini",
    }

    env_vars.update(override_env_param_dict)

    for key, value in env_vars.items():
        if key in exclude_list:
            monkeypatch.delenv(key, raising=False)
            continue
        monkeypatch.setenv(key, value)

    return env_vars
