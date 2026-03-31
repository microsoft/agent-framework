# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import os
from functools import wraps
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from agent_framework.exceptions import SettingNotFoundError
from azure.core.credentials_async import AsyncTokenCredential
from azure.identity.aio import AzureCliCredential
from openai import AsyncAzureOpenAI

from agent_framework_openai import OpenAIEmbeddingClient, OpenAIEmbeddingOptions

pytestmark = pytest.mark.azure

skip_if_azure_openai_integration_tests_disabled = pytest.mark.skipif(
    os.getenv("AZURE_OPENAI_ENDPOINT", "") in ("", "https://test-endpoint.openai.azure.com")
    or (
        os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME", "") == ""
        and os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "") == ""
    ),
    reason="No real Azure OpenAI endpoint or embedding deployment provided; skipping integration tests.",
)


def _with_azure_openai_debug() -> Any:
    def decorator(func: Any) -> Any:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await func(*args, **kwargs)
            except Exception as exc:
                model = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME") or os.getenv(
                    "AZURE_OPENAI_DEPLOYMENT_NAME", "<unset>"
                )
                api_version = os.getenv("AZURE_OPENAI_API_VERSION", "<unset>")
                endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "<unset>")
                debug_message = f"Azure OpenAI debug: endpoint={endpoint}, model={model}, api_version={api_version}"
                if hasattr(exc, "add_note"):
                    exc.add_note(debug_message)
                elif exc.args:
                    exc.args = (f"{exc.args[0]}\n{debug_message}", *exc.args[1:])
                else:
                    exc.args = (debug_message,)
                raise

        return wrapper

    return decorator


def _get_azure_embedding_deployment_name() -> str:
    return os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME") or os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"]


def _create_azure_embedding_client(
    *,
    api_key: str | None = None,
    credential: AsyncTokenCredential | None = None,
) -> OpenAIEmbeddingClient:
    resolved_api_key = (
        api_key if api_key is not None else None if credential is not None else os.environ["AZURE_OPENAI_API_KEY"]
    )
    return OpenAIEmbeddingClient(
        model=_get_azure_embedding_deployment_name(),
        api_key=resolved_api_key,
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
        credential=credential,
    )


def test_init_with_azure_endpoint(azure_openai_unit_test_env: dict[str, str]) -> None:
    client = _create_azure_embedding_client()

    assert client.model == azure_openai_unit_test_env["AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME"]
    assert isinstance(client.client, AsyncAzureOpenAI)
    assert client.OTEL_PROVIDER_NAME == "azure.ai.openai"
    assert client.azure_endpoint == azure_openai_unit_test_env["AZURE_OPENAI_ENDPOINT"]
    assert client.api_version == azure_openai_unit_test_env["AZURE_OPENAI_API_VERSION"]


def test_init_auto_detects_azure_embedding_env(azure_openai_unit_test_env: dict[str, str]) -> None:
    client = OpenAIEmbeddingClient()

    assert client.model == azure_openai_unit_test_env["AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME"]
    assert isinstance(client.client, AsyncAzureOpenAI)
    assert client.azure_endpoint == azure_openai_unit_test_env["AZURE_OPENAI_ENDPOINT"]


def test_init_falls_back_to_generic_azure_deployment_env(
    monkeypatch, azure_openai_unit_test_env: dict[str, str]
) -> None:
    monkeypatch.delenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME", raising=False)

    client = OpenAIEmbeddingClient()

    assert client.model == azure_openai_unit_test_env["AZURE_OPENAI_DEPLOYMENT_NAME"]
    assert isinstance(client.client, AsyncAzureOpenAI)


def test_init_does_not_fall_back_to_openai_embedding_model_for_azure_env(
    monkeypatch, azure_openai_unit_test_env: dict[str, str]
) -> None:
    monkeypatch.delenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT_NAME", raising=False)
    monkeypatch.setenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

    with pytest.raises(SettingNotFoundError, match="Azure OpenAI client requires a deployment name"):
        OpenAIEmbeddingClient()


def test_init_does_not_fall_back_to_openai_model_for_azure_env(
    monkeypatch, azure_openai_unit_test_env: dict[str, str]
) -> None:
    monkeypatch.delenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT_NAME", raising=False)
    monkeypatch.delenv("OPENAI_EMBEDDING_MODEL", raising=False)
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5")

    with pytest.raises(SettingNotFoundError, match="Azure OpenAI client requires a deployment name"):
        OpenAIEmbeddingClient()


def test_openai_api_key_wins_over_azure_env(monkeypatch, azure_openai_unit_test_env: dict[str, str]) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-dummy-key")
    monkeypatch.setenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

    client = OpenAIEmbeddingClient()

    assert client.model == "text-embedding-3-small"
    assert not isinstance(client.client, AsyncAzureOpenAI)
    assert client.azure_endpoint is None


def test_api_version_alone_does_not_override_openai_api_key(
    monkeypatch, azure_openai_unit_test_env: dict[str, str]
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-dummy-key")
    monkeypatch.setenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

    client = OpenAIEmbeddingClient(api_version="2024-10-21")

    assert client.model == "text-embedding-3-small"
    assert not isinstance(client.client, AsyncAzureOpenAI)
    assert client.azure_endpoint is None


def test_explicit_credential_wins_over_openai_api_key(monkeypatch, azure_openai_unit_test_env: dict[str, str]) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-dummy-key")
    monkeypatch.setenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

    client = OpenAIEmbeddingClient(credential=lambda: "token")

    assert client.model == azure_openai_unit_test_env["AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME"]
    assert isinstance(client.client, AsyncAzureOpenAI)
    assert client.azure_endpoint == azure_openai_unit_test_env["AZURE_OPENAI_ENDPOINT"]


def test_init_with_credential_wraps_async_token_credential(
    monkeypatch, azure_openai_unit_test_env: dict[str, str]
) -> None:
    class TestAsyncTokenCredential(AsyncTokenCredential):
        async def get_token(self, *scopes: str, **kwargs: object):
            raise NotImplementedError

    monkeypatch.setenv("OPENAI_API_KEY", "test-dummy-key")
    monkeypatch.setenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    credential = TestAsyncTokenCredential()
    token_provider = MagicMock()

    with patch("azure.identity.aio.get_bearer_token_provider", return_value=token_provider) as mock_provider:
        client = OpenAIEmbeddingClient(credential=credential)

    assert isinstance(client.client, AsyncAzureOpenAI)
    assert client.model == azure_openai_unit_test_env["AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME"]
    mock_provider.assert_called_once_with(credential, "https://cognitiveservices.azure.com/.default")


@pytest.mark.parametrize("exclude_list", [["AZURE_OPENAI_API_VERSION"]], indirect=True)
def test_init_uses_default_azure_api_version(azure_openai_unit_test_env: dict[str, str]) -> None:
    client = _create_azure_embedding_client()

    assert client.model == azure_openai_unit_test_env["AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME"]
    assert client.api_version == "2024-10-21"


def test_openai_base_url_wins_over_azure_aliases(monkeypatch, azure_openai_unit_test_env: dict[str, str]) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-dummy-key")
    monkeypatch.setenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://custom-openai-endpoint.com/v1")

    client = OpenAIEmbeddingClient()

    assert client.model == "text-embedding-3-small"
    assert not isinstance(client.client, AsyncAzureOpenAI)
    assert client.azure_endpoint is None


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_openai_integration_tests_disabled
@_with_azure_openai_debug()
async def test_azure_openai_get_embeddings() -> None:
    async with AzureCliCredential() as credential:
        client = _create_azure_embedding_client(credential=credential)

        result = await client.get_embeddings(["hello world"])

    assert len(result) == 1
    assert isinstance(result[0].vector, list)
    assert len(result[0].vector) > 0
    assert all(isinstance(v, float) for v in result[0].vector)
    assert result[0].model is not None
    assert result.usage is not None
    assert result.usage["input_token_count"] > 0


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_openai_integration_tests_disabled
@_with_azure_openai_debug()
async def test_azure_openai_get_embeddings_multiple() -> None:
    async with AzureCliCredential() as credential:
        client = _create_azure_embedding_client(credential=credential)

        result = await client.get_embeddings(["hello", "world", "test"])

    assert len(result) == 3
    dims = [len(embedding.vector) for embedding in result]
    assert all(dimension == dims[0] for dimension in dims)


@pytest.mark.flaky
@pytest.mark.integration
@skip_if_azure_openai_integration_tests_disabled
@_with_azure_openai_debug()
async def test_azure_openai_get_embeddings_with_dimensions() -> None:
    async with AzureCliCredential() as credential:
        client = _create_azure_embedding_client(credential=credential)

        options: OpenAIEmbeddingOptions = {"dimensions": 256}
        result = await client.get_embeddings(["hello world"], options=options)

    assert len(result) == 1
    assert len(result[0].vector) == 256
