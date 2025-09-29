# Copyright (c) Microsoft. All rights reserved.

from unittest.mock import AsyncMock, MagicMock

import pytest
from azure.core.exceptions import ClientAuthenticationError

from agent_framework.azure._entra_id_authentication import (
    get_entra_auth_token,
    get_entra_auth_token_async,
)
from agent_framework.exceptions import ServiceInvalidAuthError


@pytest.fixture
def mock_credential() -> MagicMock:
    """Mock synchronous TokenCredential."""
    mock_cred = MagicMock()
    # Create a mock token object with a .token attribute
    mock_token = MagicMock()
    mock_token.token = "test-access-token-12345"
    mock_cred.get_token.return_value = mock_token
    return mock_cred


@pytest.fixture
def mock_async_credential() -> MagicMock:
    """Mock asynchronous AsyncTokenCredential."""
    mock_cred = MagicMock()
    # Create a mock token object with a .token attribute
    mock_token = MagicMock()
    mock_token.token = "test-async-access-token-12345"
    mock_cred.get_token = AsyncMock(return_value=mock_token)
    return mock_cred


def test_get_entra_auth_token_success(mock_credential: MagicMock) -> None:
    """Test successful token retrieval with sync function."""

    token_endpoint = "https://test-endpoint.com/.default"

    result = get_entra_auth_token(mock_credential, token_endpoint)

    # Assert - check the results
    assert result == "test-access-token-12345"
    mock_credential.get_token.assert_called_once_with(token_endpoint)


async def test_get_entra_auth_token_async_success(mock_async_credential: MagicMock) -> None:
    """Test successful token retrieval with async function."""

    token_endpoint = "https://test-endpoint.com/.default"

    result = await get_entra_auth_token_async(mock_async_credential, token_endpoint)

    # Assert - check the results
    assert result == "test-async-access-token-12345"
    mock_async_credential.get_token.assert_called_once_with(token_endpoint)


def test_get_entra_auth_token_missing_endpoint(mock_credential: MagicMock) -> None:
    """Test that missing token endpoint raises ServiceInvalidAuthError."""
    # Test with empty string
    with pytest.raises(ServiceInvalidAuthError, match="A token endpoint must be provided"):
        get_entra_auth_token(mock_credential, "")

    # Test with None
    with pytest.raises(ServiceInvalidAuthError, match="A token endpoint must be provided"):
        get_entra_auth_token(mock_credential, None)  # type: ignore


async def test_get_entra_auth_token_async_missing_endpoint(mock_async_credential: MagicMock) -> None:
    """Test that missing token endpoint raises ServiceInvalidAuthError in async function."""
    # Test with empty string
    with pytest.raises(ServiceInvalidAuthError, match="A token endpoint must be provided"):
        await get_entra_auth_token_async(mock_async_credential, "")

    # Test with None
    with pytest.raises(ServiceInvalidAuthError, match="A token endpoint must be provided"):
        await get_entra_auth_token_async(mock_async_credential, None)  # type: ignore


def test_get_entra_auth_token_auth_failure(mock_credential: MagicMock) -> None:
    """Test that Azure authentication failure returns None."""

    mock_credential.get_token.side_effect = ClientAuthenticationError("Auth failed")
    token_endpoint = "https://test-endpoint.com/.default"

    result = get_entra_auth_token(mock_credential, token_endpoint)

    # Assert - should return None on auth failure
    assert result is None
    mock_credential.get_token.assert_called_once_with(token_endpoint)


async def test_get_entra_auth_token_async_auth_failure(mock_async_credential: MagicMock) -> None:
    """Test that Azure authentication failure returns None in async function."""

    mock_async_credential.get_token.side_effect = ClientAuthenticationError("Auth failed")
    token_endpoint = "https://test-endpoint.com/.default"

    result = await get_entra_auth_token_async(mock_async_credential, token_endpoint)

    # Assert - should return None on auth failure
    assert result is None
    mock_async_credential.get_token.assert_called_once_with(token_endpoint)


def test_get_entra_auth_token_none_token_response(mock_credential: MagicMock) -> None:
    """Test that None token response returns None."""
    mock_credential.get_token.return_value = None
    token_endpoint = "https://test-endpoint.com/.default"

    result = get_entra_auth_token(mock_credential, token_endpoint)

    # Assert
    assert result is None
    mock_credential.get_token.assert_called_once_with(token_endpoint)


async def test_get_entra_auth_token_async_none_token_response(mock_async_credential: MagicMock) -> None:
    """Test that None token response returns None in async function."""
    mock_async_credential.get_token.return_value = None
    token_endpoint = "https://test-endpoint.com/.default"

    result = await get_entra_auth_token_async(mock_async_credential, token_endpoint)

    # Assert
    assert result is None
    mock_async_credential.get_token.assert_called_once_with(token_endpoint)


def test_get_entra_auth_token_with_kwargs(mock_credential: MagicMock) -> None:
    """Test that kwargs are passed through to get_token."""

    token_endpoint = "https://test-endpoint.com/.default"
    extra_kwargs = {"scopes": ["read", "write"], "tenant_id": "test-tenant"}

    result = get_entra_auth_token(mock_credential, token_endpoint, **extra_kwargs)

    # Assert
    assert result == "test-access-token-12345"
    mock_credential.get_token.assert_called_once_with(token_endpoint, **extra_kwargs)


async def test_get_entra_auth_token_async_with_kwargs(mock_async_credential: MagicMock) -> None:
    """Test that kwargs are passed through to async get_token."""

    token_endpoint = "https://test-endpoint.com/.default"
    extra_kwargs = {"scopes": ["read", "write"], "tenant_id": "test-tenant"}

    result = await get_entra_auth_token_async(mock_async_credential, token_endpoint, **extra_kwargs)

    # Assert
    assert result == "test-async-access-token-12345"
    mock_async_credential.get_token.assert_called_once_with(token_endpoint, **extra_kwargs)
