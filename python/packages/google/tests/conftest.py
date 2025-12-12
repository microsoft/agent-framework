# Copyright (c) Microsoft. All rights reserved.
import os
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


@fixture
def google_ai_unit_test_env(monkeypatch, exclude_list, override_env_param_dict):  # type: ignore
    """Fixture to set environment variables for GoogleAISettings."""
    if exclude_list is None:
        exclude_list = []

    if override_env_param_dict is None:
        override_env_param_dict = {}

    # Ensure tests are deterministic regardless of the machine environment.
    for key in list(os.environ):
        if key.startswith("GOOGLE_AI_"):
            monkeypatch.delenv(key, raising=False)  # type: ignore

    env_vars = {
        "GOOGLE_AI_API_KEY": "test-api-key-12345",
        "GOOGLE_AI_CHAT_MODEL_ID": "gemini-1.5-pro",
    }

    env_vars.update(override_env_param_dict)  # type: ignore

    for key, value in env_vars.items():
        if key in exclude_list:
            monkeypatch.delenv(key, raising=False)  # type: ignore
            continue
        monkeypatch.setenv(key, value)  # type: ignore

    return env_vars
