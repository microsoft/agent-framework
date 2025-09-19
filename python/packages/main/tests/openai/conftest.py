# Copyright (c) Microsoft. All rights reserved.
from typing import Any

from pytest import fixture


# region Connector Settings fixtures
@fixture
def exclude_list(request: Any) -> list[str]:
    """Fixture that returns a list of environment variables to exclude."""
    return request.param if hasattr(request, "param") else []


@fixture
def override_env_param_dict(request: Any) -> dict[str, str]:
    """Fixture that returns a dict of environment variables to override."""
    return request.param if hasattr(request, "param") else {}


@fixture()
def openai_unit_test_env(monkeypatch, exclude_list, override_env_param_dict):  # type: ignore
    """Fixture to set environment variables for OpenAISettings."""

    if exclude_list is None:
        exclude_list = []

    if override_env_param_dict is None:
        override_env_param_dict = {}

    env_vars = {
        "OPENAI_API_KEY": "test-dummy-key",
        "OPENAI_ORG_ID": "test_org_id",
        "OPENAI_RESPONSES_MODEL_ID": "test_responses_model_id",
        "OPENAI_CHAT_MODEL_ID": "test_chat_model_id",
        "OPENAI_TEXT_MODEL_ID": "test_text_model_id",
        "OPENAI_EMBEDDING_MODEL_ID": "test_embedding_model_id",
        "OPENAI_TEXT_TO_IMAGE_MODEL_ID": "test_text_to_image_model_id",
        "OPENAI_AUDIO_TO_TEXT_MODEL_ID": "test_audio_to_text_model_id",
        "OPENAI_TEXT_TO_AUDIO_MODEL_ID": "test_text_to_audio_model_id",
        "OPENAI_REALTIME_MODEL_ID": "test_realtime_model_id",
    }

    env_vars.update(override_env_param_dict)  # type: ignore

    for key, value in env_vars.items():
        if key in exclude_list:
            monkeypatch.delenv(key, raising=False)  # type: ignore
            continue
        monkeypatch.setenv(key, value)  # type: ignore

    return env_vars
