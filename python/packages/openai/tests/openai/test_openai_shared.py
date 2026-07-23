# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from types import TracebackType
from typing import Any, cast
from unittest.mock import MagicMock, patch

import agent_framework._telemetry as telemetry
import httpx
import pytest
from agent_framework import AGENT_FRAMEWORK_USER_AGENT
from agent_framework._telemetry import FeatureIndex as CoreFeatureIndex
from agent_framework._telemetry import mark_feature_used
from azure.core.credentials import TokenCredential
from azure.core.credentials_async import AsyncTokenCredential

from agent_framework_openai._feature_usage import create_feature_usage_http_client
from agent_framework_openai._shared import (
    AZURE_OPENAI_TOKEN_SCOPE,
    _ensure_async_token_provider,
    _resolve_azure_credential_to_token_provider,
)


class _AsyncTokenCredentialStub(AsyncTokenCredential):
    async def get_token(self, *scopes: str, **kwargs: object):
        raise NotImplementedError

    async def close(self) -> None:
        pass

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ) -> None:
        pass


class _TokenCredentialStub(TokenCredential):
    def get_token(self, *scopes: str, **kwargs: object):
        raise NotImplementedError


def test_resolve_azure_async_credential_wraps_provider() -> None:
    credential = _AsyncTokenCredentialStub()
    token_provider = MagicMock()

    with patch("azure.identity.aio.get_bearer_token_provider", return_value=token_provider) as mock_provider:
        resolved = _resolve_azure_credential_to_token_provider(credential)

    assert resolved is token_provider
    mock_provider.assert_called_once_with(credential, AZURE_OPENAI_TOKEN_SCOPE)


def test_resolve_azure_sync_credential_wraps_provider() -> None:
    credential = _TokenCredentialStub()
    token_provider = MagicMock()

    with patch("azure.identity.get_bearer_token_provider", return_value=token_provider) as mock_provider:
        resolved = _resolve_azure_credential_to_token_provider(credential)

    assert resolved is token_provider
    mock_provider.assert_called_once_with(credential, AZURE_OPENAI_TOKEN_SCOPE)


def test_resolve_azure_callable_token_provider_passthrough() -> None:
    token_provider = MagicMock()

    assert _resolve_azure_credential_to_token_provider(token_provider) is token_provider


def test_resolve_azure_invalid_credential_raises() -> None:
    with pytest.raises(ValueError, match="credential"):
        _resolve_azure_credential_to_token_provider(cast(Any, object()))


async def test_feature_usage_hook_stamps_approved_origin_and_strips_custom_origin() -> None:
    with telemetry._feature_mask_lock:
        telemetry._feature_mask = 0
    mark_feature_used(CoreFeatureIndex.CORE_AGENT)
    client = create_feature_usage_http_client()
    hook = client.event_hooks["request"][0]
    approved = httpx.Request(
        "POST",
        "https://resource.openai.azure.com/openai/v1/responses",
        headers={"User-Agent": f"{AGENT_FRAMEWORK_USER_AGENT} sdk/1.0"},
    )
    custom = httpx.Request(
        "POST",
        "https://customer-gateway.example.com/v1/responses",
        headers={"User-Agent": f"{AGENT_FRAMEWORK_USER_AGENT} (feat=v1.1)"},
    )

    await hook(approved)
    await hook(custom)
    await client.aclose()

    assert approved.headers["User-Agent"] == f"{AGENT_FRAMEWORK_USER_AGENT} sdk/1.0 (feat=v1.1)"
    assert custom.headers["User-Agent"] == AGENT_FRAMEWORK_USER_AGENT


async def test_ensure_async_token_provider_wraps_sync_provider() -> None:
    def sync_provider() -> str:
        return "sync-token"

    wrapper = _ensure_async_token_provider(sync_provider)
    result = await wrapper()

    assert result == "sync-token"


async def test_ensure_async_token_provider_wraps_async_provider() -> None:
    async def async_provider() -> str:
        return "async-token"

    wrapper = _ensure_async_token_provider(async_provider)
    result = await wrapper()

    assert result == "async-token"
