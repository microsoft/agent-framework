# Copyright (c) Microsoft. All rights reserved.

import pytest

from agent_framework import ChatClient
from agent_framework.exceptions import ServiceInitializationError
from agent_framework.openai import OpenAIChatClient


def test_init(openai_unit_test_env: dict[str, str]) -> None:
    # Test successful initialization
    open_ai_chat_completion = OpenAIChatClient()

    assert open_ai_chat_completion.ai_model_id == openai_unit_test_env["OPENAI_CHAT_MODEL_ID"]
    assert isinstance(open_ai_chat_completion, ChatClient)


def test_init_validation_fail() -> None:
    # Test successful initialization
    with pytest.raises(ServiceInitializationError):
        OpenAIChatClient(api_key="34523", ai_model_id={"test": "dict"})  # type: ignore


def test_init_ai_model_id_constructor(openai_unit_test_env: dict[str, str]) -> None:
    # Test successful initialization
    ai_model_id = "test_model_id"
    open_ai_chat_completion = OpenAIChatClient(ai_model_id=ai_model_id)

    assert open_ai_chat_completion.ai_model_id == ai_model_id
    assert isinstance(open_ai_chat_completion, ChatClient)


def test_init_with_default_header(openai_unit_test_env: dict[str, str]) -> None:
    default_headers = {"X-Unit-Test": "test-guid"}

    # Test successful initialization
    open_ai_chat_completion = OpenAIChatClient(
        default_headers=default_headers,
    )

    assert open_ai_chat_completion.ai_model_id == openai_unit_test_env["OPENAI_CHAT_MODEL_ID"]
    assert isinstance(open_ai_chat_completion, ChatClient)

    # Assert that the default header we added is present in the client's default headers
    for key, value in default_headers.items():
        assert key in open_ai_chat_completion.client.default_headers
        assert open_ai_chat_completion.client.default_headers[key] == value


@pytest.mark.parametrize("exclude_list", [["OPENAI_CHAT_MODEL_ID"]], indirect=True)
def test_init_with_empty_model_id(openai_unit_test_env: dict[str, str]) -> None:
    with pytest.raises(ServiceInitializationError):
        OpenAIChatClient(
            env_file_path="test.env",
        )


@pytest.mark.parametrize("exclude_list", [["OPENAI_API_KEY"]], indirect=True)
def test_init_with_empty_api_key(openai_unit_test_env: dict[str, str]) -> None:
    ai_model_id = "test_model_id"

    with pytest.raises(ServiceInitializationError):
        OpenAIChatClient(
            ai_model_id=ai_model_id,
            env_file_path="test.env",
        )


def test_serialize(openai_unit_test_env: dict[str, str]) -> None:
    default_headers = {"X-Unit-Test": "test-guid"}

    settings = {
        "ai_model_id": openai_unit_test_env["OPENAI_CHAT_MODEL_ID"],
        "api_key": openai_unit_test_env["OPENAI_API_KEY"],
        "default_headers": default_headers,
    }

    open_ai_chat_completion = OpenAIChatClient.from_dict(settings)
    dumped_settings = open_ai_chat_completion.to_dict()
    assert dumped_settings["ai_model_id"] == openai_unit_test_env["OPENAI_CHAT_MODEL_ID"]
    assert dumped_settings["api_key"] == openai_unit_test_env["OPENAI_API_KEY"]
    # Assert that the default header we added is present in the dumped_settings default headers
    for key, value in default_headers.items():
        assert key in dumped_settings["default_headers"]
        assert dumped_settings["default_headers"][key] == value
    # Assert that the 'User-Agent' header is not present in the dumped_settings default headers
    assert "User-Agent" not in dumped_settings["default_headers"]


def test_serialize_with_org_id(openai_unit_test_env: dict[str, str]) -> None:
    settings = {
        "ai_model_id": openai_unit_test_env["OPENAI_CHAT_MODEL_ID"],
        "api_key": openai_unit_test_env["OPENAI_API_KEY"],
        "org_id": openai_unit_test_env["OPENAI_ORG_ID"],
    }

    open_ai_chat_completion = OpenAIChatClient.from_dict(settings)
    dumped_settings = open_ai_chat_completion.to_dict()
    assert dumped_settings["ai_model_id"] == openai_unit_test_env["OPENAI_CHAT_MODEL_ID"]
    assert dumped_settings["api_key"] == openai_unit_test_env["OPENAI_API_KEY"]
    assert dumped_settings["org_id"] == openai_unit_test_env["OPENAI_ORG_ID"]
    # Assert that the 'User-Agent' header is not present in the dumped_settings default headers
    assert "User-Agent" not in dumped_settings["default_headers"]
