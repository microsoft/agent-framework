# Copyright (c) Microsoft. All rights reserved.

import inspect

import pytest
from agent_framework import Agent, SupportsChatGetResponse
from agent_framework._settings import load_settings
from agent_framework.edenai import EdenAIChatClient
from agent_framework.exceptions import SettingNotFoundError

from agent_framework_edenai._chat_client import DEFAULT_EDENAI_BASE_URL, EdenAISettings

# Settings Tests


def test_edenai_settings_init_from_env(edenai_unit_test_env: dict[str, str]) -> None:
    """Test EdenAISettings initialization from environment variables."""
    settings = load_settings(EdenAISettings, env_prefix="EDENAI_")

    assert settings["api_key"] == edenai_unit_test_env["EDENAI_API_KEY"]
    assert settings["model"] == edenai_unit_test_env["EDENAI_MODEL"]


def test_edenai_settings_init_with_explicit_values() -> None:
    """Test EdenAISettings initialization with explicit values."""
    settings = load_settings(
        EdenAISettings,
        env_prefix="EDENAI_",
        api_key="explicit-key",
        model="anthropic/claude-sonnet-4-5",
    )

    assert settings["api_key"] == "explicit-key"
    assert settings["model"] == "anthropic/claude-sonnet-4-5"


@pytest.mark.parametrize("exclude_list", [["EDENAI_API_KEY"]], indirect=True)
def test_edenai_settings_missing_api_key(edenai_unit_test_env: dict[str, str]) -> None:
    """Test EdenAISettings when api_key is missing raises error."""
    with pytest.raises(SettingNotFoundError, match="Required setting 'api_key'"):
        load_settings(
            EdenAISettings,
            env_prefix="EDENAI_",
            required_fields=["api_key"],
        )


@pytest.mark.parametrize("exclude_list", [["EDENAI_MODEL"]], indirect=True)
def test_edenai_settings_missing_model(edenai_unit_test_env: dict[str, str]) -> None:
    """Test EdenAISettings when model is missing raises error."""
    with pytest.raises(SettingNotFoundError, match="Required setting 'model'"):
        load_settings(
            EdenAISettings,
            env_prefix="EDENAI_",
            required_fields=["model"],
        )


def test_edenai_settings_explicit_overrides_env(edenai_unit_test_env: dict[str, str]) -> None:
    """Test that explicit values override environment variables."""
    settings = load_settings(EdenAISettings, env_prefix="EDENAI_", model="google/gemini-2.5-flash")

    assert settings["model"] == "google/gemini-2.5-flash"
    assert settings["model"] != edenai_unit_test_env["EDENAI_MODEL"]


# Client Initialization Tests


def test_edenai_client_init(edenai_unit_test_env: dict[str, str]) -> None:
    """Test EdenAIChatClient initialization from environment variables."""
    client = EdenAIChatClient()

    assert client.model == edenai_unit_test_env["EDENAI_MODEL"]
    assert isinstance(client, SupportsChatGetResponse)


def test_edenai_client_init_with_explicit_values() -> None:
    """Test EdenAIChatClient initialization with explicit api_key and model."""
    client = EdenAIChatClient(model="openai/gpt-4o-mini", api_key="explicit-key")

    assert client.model == "openai/gpt-4o-mini"


def test_edenai_client_default_base_url(edenai_unit_test_env: dict[str, str]) -> None:
    """Test EdenAIChatClient uses the Eden AI base URL by default."""
    client = EdenAIChatClient()

    assert str(client.client.base_url).rstrip("/") == DEFAULT_EDENAI_BASE_URL


def test_edenai_client_base_url_override(edenai_unit_test_env: dict[str, str]) -> None:
    """Test EdenAIChatClient honors a base_url override."""
    client = EdenAIChatClient(base_url="https://example.test/v3")

    assert str(client.client.base_url).rstrip("/") == "https://example.test/v3"


def test_edenai_client_missing_api_key(edenai_unit_test_env: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    """Test EdenAIChatClient raises when the api key is missing."""
    monkeypatch.delenv("EDENAI_API_KEY", raising=False)
    with pytest.raises(SettingNotFoundError, match="Required setting 'api_key'"):
        EdenAIChatClient(model="openai/gpt-4o-mini")


def test_agent_accepts_edenai_client(edenai_unit_test_env: dict[str, str]) -> None:
    """Test that an Agent accepts an EdenAIChatClient."""
    client = EdenAIChatClient()
    agent = Agent(client=client, instructions="test agent")
    assert agent.client is client


def test_edenai_client_get_response_uses_explicit_runtime_buckets() -> None:
    """Eden AI should expose explicit runtime buckets instead of raw kwargs."""
    signature = inspect.signature(EdenAIChatClient.get_response)

    assert "client_kwargs" in signature.parameters
    assert "function_invocation_kwargs" in signature.parameters
    assert all(parameter.kind != inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values())
