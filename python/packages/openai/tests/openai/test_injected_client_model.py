# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from openai import AsyncAzureOpenAI, AsyncOpenAI

from agent_framework_openai import OpenAIChatClient, OpenAIChatCompletionClient, OpenAIEmbeddingClient

pytestmark = pytest.mark.azure

_AZURE_CLIENTS = [
    pytest.param(OpenAIChatClient, "AZURE_OPENAI_CHAT_MODEL", id="chat"),
    pytest.param(OpenAIChatCompletionClient, "AZURE_OPENAI_CHAT_COMPLETION_MODEL", id="chat-completion"),
    pytest.param(OpenAIEmbeddingClient, "AZURE_OPENAI_EMBEDDING_MODEL", id="embedding"),
]

_OPENAI_CLIENTS = [
    pytest.param(OpenAIChatClient, "OPENAI_CHAT_MODEL", id="chat"),
    pytest.param(OpenAIChatCompletionClient, "OPENAI_CHAT_COMPLETION_MODEL", id="chat-completion"),
    pytest.param(OpenAIEmbeddingClient, "OPENAI_EMBEDDING_MODEL", id="embedding"),
]


@pytest.mark.parametrize(("client_cls", "specific_env"), _AZURE_CLIENTS)
def test_injected_azure_deployment_wins_over_environment(
    client_cls: type[Any],
    specific_env: str,
    monkeypatch: pytest.MonkeyPatch,
    azure_openai_unit_test_env: dict[str, str],
    azure_sdk_client_factory: Callable[[str | None], AsyncAzureOpenAI],
) -> None:
    monkeypatch.setenv(specific_env, "env-specific")
    monkeypatch.setenv("AZURE_OPENAI_MODEL", "env-generic")
    sdk_client = azure_sdk_client_factory("client-deployment")

    client = client_cls(async_client=sdk_client)

    assert client.model == "client-deployment"
    assert client.client is sdk_client
    assert sdk_client._azure_deployment == "client-deployment"
    assert azure_openai_unit_test_env[specific_env]


@pytest.mark.parametrize(("client_cls", "specific_env"), _AZURE_CLIENTS)
def test_explicit_model_wins_over_injected_deployment_and_environment(
    client_cls: type[Any],
    specific_env: str,
    monkeypatch: pytest.MonkeyPatch,
    azure_openai_unit_test_env: dict[str, str],
    azure_sdk_client_factory: Callable[[str | None], AsyncAzureOpenAI],
) -> None:
    monkeypatch.setenv(specific_env, "env-specific")
    monkeypatch.setenv("AZURE_OPENAI_MODEL", "env-generic")
    sdk_client = azure_sdk_client_factory("client-deployment")

    client = client_cls(model="explicit-deployment", async_client=sdk_client)

    assert client.model == "explicit-deployment"
    assert client.client is sdk_client
    assert sdk_client._azure_deployment == "client-deployment"
    assert azure_openai_unit_test_env["AZURE_OPENAI_MODEL"]


@pytest.mark.parametrize(("client_cls", "specific_env"), _AZURE_CLIENTS)
def test_injected_azure_client_without_deployment_keeps_environment_fallback(
    client_cls: type[Any],
    specific_env: str,
    azure_openai_unit_test_env: dict[str, str],
    azure_sdk_client_factory: Callable[[str | None], AsyncAzureOpenAI],
) -> None:
    sdk_client = azure_sdk_client_factory(None)

    client = client_cls(async_client=sdk_client)

    assert client.model == azure_openai_unit_test_env[specific_env]
    assert client.client is sdk_client


@pytest.mark.parametrize(("client_cls", "specific_env"), _OPENAI_CLIENTS)
def test_injected_openai_client_uses_openai_environment(
    client_cls: type[Any],
    specific_env: str,
    monkeypatch: pytest.MonkeyPatch,
    openai_unit_test_env: dict[str, str],
) -> None:
    monkeypatch.setenv(specific_env, "openai-specific")
    monkeypatch.setenv("AZURE_OPENAI_CHAT_MODEL", "azure-chat")
    monkeypatch.setenv("AZURE_OPENAI_CHAT_COMPLETION_MODEL", "azure-chat-completion")
    monkeypatch.setenv("AZURE_OPENAI_EMBEDDING_MODEL", "azure-embedding")
    monkeypatch.setenv("AZURE_OPENAI_MODEL", "azure-generic")
    sdk_client = AsyncOpenAI(api_key="dummy")

    client = client_cls(async_client=sdk_client)

    assert client.model == "openai-specific"
    assert client.client is sdk_client
    assert openai_unit_test_env["OPENAI_MODEL"]


@pytest.mark.parametrize(("client_cls", "specific_env"), _OPENAI_CLIENTS)
def test_explicit_model_wins_for_injected_openai_client(
    client_cls: type[Any],
    specific_env: str,
    monkeypatch: pytest.MonkeyPatch,
    openai_unit_test_env: dict[str, str],
) -> None:
    monkeypatch.setenv(specific_env, "openai-specific")
    sdk_client = AsyncOpenAI(api_key="dummy")

    client = client_cls(model="explicit-model", async_client=sdk_client)

    assert client.model == "explicit-model"
    assert client.client is sdk_client
    assert openai_unit_test_env["OPENAI_API_KEY"]
