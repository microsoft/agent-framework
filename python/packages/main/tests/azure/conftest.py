# Copyright (c) Microsoft. All rights reserved.
from typing import Any

from pytest import fixture

from agent_framework import ChatMessage


# region: Connector Settings fixtures
@fixture
def exclude_list(request: Any) -> list[str]:
    """Fixture that returns a list of environment variables to exclude."""
    return request.param if hasattr(request, "param") else []


@fixture
def override_env_param_dict(request: Any) -> dict[str, str]:
    """Fixture that returns a dict of environment variables to override."""
    return request.param if hasattr(request, "param") else {}


# These two fixtures are used for multiple things, also non-connector tests
@fixture()
def azure_openai_unit_test_env(monkeypatch, exclude_list, override_env_param_dict):  # type: ignore
    """Fixture to set environment variables for AzureOpenAISettings."""

    if exclude_list is None:
        exclude_list = []

    if override_env_param_dict is None:
        override_env_param_dict = {}

    env_vars = {
        "AZURE_OPENAI_ENDPOINT": "https://test-endpoint.com",
        "AZURE_OPENAI_CHAT_DEPLOYMENT_NAME": "test_chat_deployment",
        "AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME": "test_chat_deployment",
        "AZURE_OPENAI_TEXT_DEPLOYMENT_NAME": "test_text_deployment",
        "AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME": "test_embedding_deployment",
        "AZURE_OPENAI_TEXT_TO_IMAGE_DEPLOYMENT_NAME": "test_text_to_image_deployment",
        "AZURE_OPENAI_AUDIO_TO_TEXT_DEPLOYMENT_NAME": "test_audio_to_text_deployment",
        "AZURE_OPENAI_TEXT_TO_AUDIO_DEPLOYMENT_NAME": "test_text_to_audio_deployment",
        "AZURE_OPENAI_REALTIME_DEPLOYMENT_NAME": "test_realtime_deployment",
        "AZURE_OPENAI_API_KEY": "test_api_key",
        "AZURE_OPENAI_API_VERSION": "2023-03-15-preview",
        "AZURE_OPENAI_BASE_URL": "https://test_text_deployment.test-base-url.com",
        "AZURE_OPENAI_TOKEN_ENDPOINT": "https://test-token-endpoint.com",
    }

    env_vars.update(override_env_param_dict)  # type: ignore

    for key, value in env_vars.items():
        if key in exclude_list:
            monkeypatch.delenv(key, raising=False)  # type: ignore
            continue
        monkeypatch.setenv(key, value)  # type: ignore

    return env_vars


@fixture(scope="function")
def chat_history() -> list[ChatMessage]:
    return []
