# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from azure.core.credentials import TokenCredential
from azure.core.credentials_async import AsyncTokenCredential

from agent_framework_openai._shared import AZURE_OPENAI_TOKEN_SCOPE, _resolve_azure_credential_to_token_provider


class _AsyncTokenCredentialStub(AsyncTokenCredential):
    async def get_token(self, *scopes: str, **kwargs: object):
        raise NotImplementedError


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
        _resolve_azure_credential_to_token_provider(object())  # type: ignore[arg-type]
