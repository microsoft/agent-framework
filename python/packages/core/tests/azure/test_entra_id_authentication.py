# Copyright (c) Microsoft. All rights reserved.

from unittest.mock import MagicMock, patch

import pytest
from azure.core.credentials import TokenCredential
from azure.core.credentials_async import AsyncTokenCredential

from agent_framework.azure._entra_id_authentication import (
    resolve_credential_to_token_provider,
)
from agent_framework.exceptions import ChatClientInvalidAuthException

TOKEN_ENDPOINT = "https://cognitiveservices.azure.com/.default"


def test_resolve_sync_credential_returns_provider() -> None:
    """Test that a sync TokenCredential is resolved via azure.identity.get_bearer_token_provider."""
    mock_credential = MagicMock(spec=TokenCredential)
    mock_provider = MagicMock(return_value="token-string")

    with patch("azure.identity.get_bearer_token_provider", return_value=mock_provider) as mock_gbtp:
        result = resolve_credential_to_token_provider(mock_credential, TOKEN_ENDPOINT)

    mock_gbtp.assert_called_once_with(mock_credential, TOKEN_ENDPOINT)
    assert result is mock_provider


def test_resolve_async_credential_returns_provider() -> None:
    """Test that an AsyncTokenCredential is resolved via azure.identity.aio.get_bearer_token_provider."""
    mock_credential = MagicMock(spec=AsyncTokenCredential)
    mock_provider = MagicMock(return_value="token-string")

    with patch("azure.identity.aio.get_bearer_token_provider", return_value=mock_provider) as mock_gbtp:
        result = resolve_credential_to_token_provider(mock_credential, TOKEN_ENDPOINT)

    mock_gbtp.assert_called_once_with(mock_credential, TOKEN_ENDPOINT)
    assert result is mock_provider


def test_resolve_callable_provider_passthrough() -> None:
    """Test that a callable token provider is returned as-is, without needing token_endpoint."""
    my_provider = lambda: "my-token"  # noqa: E731

    # Works with token_endpoint
    assert resolve_credential_to_token_provider(my_provider, TOKEN_ENDPOINT) is my_provider

    # Also works without token_endpoint
    assert resolve_credential_to_token_provider(my_provider, None) is my_provider
    assert resolve_credential_to_token_provider(my_provider, "") is my_provider


def test_resolve_missing_endpoint_raises() -> None:
    """Test that missing token endpoint raises ChatClientInvalidAuthException."""
    mock_credential = MagicMock(spec=TokenCredential)

    with pytest.raises(ChatClientInvalidAuthException, match="A token endpoint must be provided"):
        resolve_credential_to_token_provider(mock_credential, "")

    with pytest.raises(ChatClientInvalidAuthException, match="A token endpoint must be provided"):
        resolve_credential_to_token_provider(mock_credential, None)  # type: ignore[arg-type]
