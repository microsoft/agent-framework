# Copyright (c) Microsoft. All rights reserved.

from unittest.mock import MagicMock, patch

import pytest
from agent_framework.exceptions import ServiceException

from agent_framework_copilotstudio._acquire_token import DEFAULT_SCOPES, acquire_token


class TestAcquireToken:
    """Test class for token acquisition functionality."""

    def test_acquire_token_missing_client_id(self) -> None:
        """Test that acquire_token raises ServiceException when client_id is missing."""
        with pytest.raises(ServiceException, match="Client ID is required for token acquisition"):
            acquire_token(client_id="", tenant_id="test-tenant-id")

    def test_acquire_token_missing_tenant_id(self) -> None:
        """Test that acquire_token raises ServiceException when tenant_id is missing."""
        with pytest.raises(ServiceException, match="Tenant ID is required for token acquisition"):
            acquire_token(client_id="test-client-id", tenant_id="")

    def test_acquire_token_none_client_id(self) -> None:
        """Test that acquire_token raises ServiceException when client_id is None."""
        with pytest.raises(ServiceException, match="Client ID is required for token acquisition"):
            acquire_token(client_id=None, tenant_id="test-tenant-id")  # type: ignore

    def test_acquire_token_none_tenant_id(self) -> None:
        """Test that acquire_token raises ServiceException when tenant_id is None."""
        with pytest.raises(ServiceException, match="Tenant ID is required for token acquisition"):
            acquire_token(client_id="test-client-id", tenant_id=None)  # type: ignore

    @patch("agent_framework_copilotstudio._acquire_token.PublicClientApplication")
    def test_acquire_token_silent_success(self, mock_pca_class: MagicMock) -> None:
        """Test successful silent token acquisition."""
        mock_pca = MagicMock()
        mock_pca_class.return_value = mock_pca

        mock_account = MagicMock()
        mock_pca.get_accounts.return_value = [mock_account]

        mock_token_response = {"access_token": "test-access-token-12345"}
        mock_pca.acquire_token_silent.return_value = mock_token_response

        result = acquire_token(
            client_id="test-client-id",
            tenant_id="test-tenant-id",
        )

        assert result == "test-access-token-12345"
        mock_pca_class.assert_called_once_with(
            client_id="test-client-id",
            authority="https://login.microsoftonline.com/test-tenant-id",
            token_cache=None,
        )
        mock_pca.get_accounts.assert_called_once_with(username=None)
        mock_pca.acquire_token_silent.assert_called_once_with(scopes=DEFAULT_SCOPES, account=mock_account)

    @patch("agent_framework_copilotstudio._acquire_token.PublicClientApplication")
    def test_acquire_token_silent_success_with_username(self, mock_pca_class: MagicMock) -> None:
        """Test successful silent token acquisition with username."""
        mock_pca = MagicMock()
        mock_pca_class.return_value = mock_pca

        mock_account = MagicMock()
        mock_pca.get_accounts.return_value = [mock_account]

        mock_token_response = {"access_token": "test-access-token-12345"}
        mock_pca.acquire_token_silent.return_value = mock_token_response

        result = acquire_token(
            client_id="test-client-id",
            tenant_id="test-tenant-id",
            username="test-user@example.com",
        )

        assert result == "test-access-token-12345"
        mock_pca.get_accounts.assert_called_once_with(username="test-user@example.com")
        mock_pca.acquire_token_silent.assert_called_once_with(scopes=DEFAULT_SCOPES, account=mock_account)

    @patch("agent_framework_copilotstudio._acquire_token.PublicClientApplication")
    def test_acquire_token_silent_success_with_custom_scopes(self, mock_pca_class: MagicMock) -> None:
        """Test successful silent token acquisition with custom scopes."""
        # Setup
        mock_pca = MagicMock()
        mock_pca_class.return_value = mock_pca

        mock_account = MagicMock()
        mock_pca.get_accounts.return_value = [mock_account]

        mock_token_response = {"access_token": "test-access-token-12345"}
        mock_pca.acquire_token_silent.return_value = mock_token_response

        custom_scopes = ["https://custom.api.com/.default"]

        result = acquire_token(
            client_id="test-client-id",
            tenant_id="test-tenant-id",
            scopes=custom_scopes,
        )

        assert result == "test-access-token-12345"
        mock_pca.acquire_token_silent.assert_called_once_with(scopes=custom_scopes, account=mock_account)

    @patch("agent_framework_copilotstudio._acquire_token.PublicClientApplication")
    def test_acquire_token_interactive_success_no_accounts(self, mock_pca_class: MagicMock) -> None:
        """Test successful interactive token acquisition when no cached accounts exist."""
        # Setup
        mock_pca = MagicMock()
        mock_pca_class.return_value = mock_pca

        mock_pca.get_accounts.return_value = []  # No cached accounts

        mock_token_response = {"access_token": "test-interactive-token-67890"}
        mock_pca.acquire_token_interactive.return_value = mock_token_response

        result = acquire_token(
            client_id="test-client-id",
            tenant_id="test-tenant-id",
        )

        assert result == "test-interactive-token-67890"
        mock_pca.acquire_token_interactive.assert_called_once_with(scopes=DEFAULT_SCOPES)

    @patch("agent_framework_copilotstudio._acquire_token.PublicClientApplication")
    def test_acquire_token_fallback_to_interactive_after_silent_fails(self, mock_pca_class: MagicMock) -> None:
        """Test fallback to interactive authentication when silent acquisition fails."""
        mock_pca = MagicMock()
        mock_pca_class.return_value = mock_pca

        mock_account = MagicMock()
        mock_pca.get_accounts.return_value = [mock_account]

        # Silent acquisition fails with error response
        mock_silent_error_response = {"error": "invalid_grant", "error_description": "Token expired"}
        mock_pca.acquire_token_silent.return_value = mock_silent_error_response

        # Interactive acquisition succeeds
        mock_interactive_response = {"access_token": "test-interactive-token-67890"}
        mock_pca.acquire_token_interactive.return_value = mock_interactive_response

        result = acquire_token(
            client_id="test-client-id",
            tenant_id="test-tenant-id",
        )

        assert result == "test-interactive-token-67890"
        mock_pca.acquire_token_silent.assert_called_once_with(scopes=DEFAULT_SCOPES, account=mock_account)
        mock_pca.acquire_token_interactive.assert_called_once_with(scopes=DEFAULT_SCOPES)

    @patch("agent_framework_copilotstudio._acquire_token.PublicClientApplication")
    def test_acquire_token_fallback_to_interactive_after_silent_exception(self, mock_pca_class: MagicMock) -> None:
        """Test fallback to interactive authentication when silent acquisition throws exception."""
        mock_pca = MagicMock()
        mock_pca_class.return_value = mock_pca

        mock_account = MagicMock()
        mock_pca.get_accounts.return_value = [mock_account]

        # Silent acquisition throws exception
        mock_pca.acquire_token_silent.side_effect = Exception("Network error")

        # Interactive acquisition succeeds
        mock_interactive_response = {"access_token": "test-interactive-token-67890"}
        mock_pca.acquire_token_interactive.return_value = mock_interactive_response

        result = acquire_token(
            client_id="test-client-id",
            tenant_id="test-tenant-id",
        )

        assert result == "test-interactive-token-67890"
        mock_pca.acquire_token_silent.assert_called_once_with(scopes=DEFAULT_SCOPES, account=mock_account)
        mock_pca.acquire_token_interactive.assert_called_once_with(scopes=DEFAULT_SCOPES)

    @patch("agent_framework_copilotstudio._acquire_token.PublicClientApplication")
    def test_acquire_token_interactive_error_response(self, mock_pca_class: MagicMock) -> None:
        """Test that acquire_token handles error responses from interactive authentication."""
        mock_pca = MagicMock()
        mock_pca_class.return_value = mock_pca

        mock_pca.get_accounts.return_value = []  # No cached accounts

        # Interactive acquisition returns error
        mock_error_response = {"error": "access_denied", "error_description": "User denied consent"}
        mock_pca.acquire_token_interactive.return_value = mock_error_response

        with pytest.raises(ServiceException, match="Authentication token cannot be acquired"):
            acquire_token(
                client_id="test-client-id",
                tenant_id="test-tenant-id",
            )

    @patch("agent_framework_copilotstudio._acquire_token.PublicClientApplication")
    def test_acquire_token_interactive_exception(self, mock_pca_class: MagicMock) -> None:
        """Test that acquire_token handles exceptions from interactive authentication."""
        mock_pca = MagicMock()
        mock_pca_class.return_value = mock_pca

        mock_pca.get_accounts.return_value = []  # No cached accounts

        # Interactive acquisition throws exception
        mock_pca.acquire_token_interactive.side_effect = Exception("Authentication service unavailable")

        with pytest.raises(ServiceException, match="Failed to acquire authentication token"):
            acquire_token(
                client_id="test-client-id",
                tenant_id="test-tenant-id",
            )

    @patch("agent_framework_copilotstudio._acquire_token.PublicClientApplication")
    def test_acquire_token_with_token_cache(self, mock_pca_class: MagicMock) -> None:
        """Test acquire_token with custom token cache."""
        mock_pca = MagicMock()
        mock_pca_class.return_value = mock_pca

        mock_account = MagicMock()
        mock_pca.get_accounts.return_value = [mock_account]

        mock_token_response = {"access_token": "test-cached-token"}
        mock_pca.acquire_token_silent.return_value = mock_token_response

        mock_token_cache = MagicMock()

        result = acquire_token(
            client_id="test-client-id",
            tenant_id="test-tenant-id",
            token_cache=mock_token_cache,
        )

        assert result == "test-cached-token"
        mock_pca_class.assert_called_once_with(
            client_id="test-client-id",
            authority="https://login.microsoftonline.com/test-tenant-id",
            token_cache=mock_token_cache,
        )

    def test_default_scopes_constant(self) -> None:
        """Test that DEFAULT_SCOPES constant is properly defined."""
        assert DEFAULT_SCOPES == ["https://api.powerplatform.com/.default"]
        assert isinstance(DEFAULT_SCOPES, list)
        assert len(DEFAULT_SCOPES) == 1
