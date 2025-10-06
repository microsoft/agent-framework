# Copyright (c) Microsoft. All rights reserved.
# pyright: reportUnknownMemberType = false
# pyright: reportUnknownVariableType = false
# pyright: reportUnknownArgumentType = false

import logging
from typing import Any

from agent_framework.exceptions import ServiceException
from msal import PublicClientApplication

logger = logging.getLogger(__name__)

# Default scopes for Power Platform API
DEFAULT_SCOPES = ["https://api.powerplatform.com/.default"]


def acquire_token(
    *,
    client_id: str,
    tenant_id: str,
    username: str | None = None,
    token_cache: Any | None = None,
    scopes: list[str] | None = None,
) -> str:
    """Acquire an authentication token using MSAL Public Client Application.

    This function attempts to acquire a token silently first (using cached tokens),
    and falls back to interactive authentication if needed.

    Keyword Args:
        client_id: The client ID of the application.
        tenant_id: The tenant ID for authentication.
        username: Optional username to filter accounts.
        token_cache: Optional token cache for storing tokens.
        scopes: Optional list of scopes. Defaults to Power Platform API scopes.

    Returns:
        The access token string.

    Raises:
        ServiceException: If authentication token cannot be acquired.
    """
    if not client_id:
        raise ServiceException("Client ID is required for token acquisition.")

    if not tenant_id:
        raise ServiceException("Tenant ID is required for token acquisition.")

    authority = f"https://login.microsoftonline.com/{tenant_id}"
    target_scopes = scopes or DEFAULT_SCOPES

    pca = PublicClientApplication(client_id=client_id, authority=authority, token_cache=token_cache)

    accounts = pca.get_accounts(username=username)

    token: str | None = None

    # Try silent token acquisition first if we have cached accounts
    if accounts:
        try:
            logger.debug("Attempting silent token acquisition")
            response = pca.acquire_token_silent(scopes=target_scopes, account=accounts[0])
            if response and "access_token" in response:
                token = str(response["access_token"])  # type: ignore[assignment]
                logger.debug("Successfully acquired token silently")
            elif response and "error" in response:
                logger.warning(
                    "Silent token acquisition failed: %s - %s", response.get("error"), response.get("error_description")
                )
        except Exception as ex:
            logger.warning("Silent token acquisition failed with exception: %s", ex)

    # Fall back to interactive authentication if silent acquisition failed
    if not token:
        try:
            logger.debug("Attempting interactive token acquisition")
            response = pca.acquire_token_interactive(scopes=target_scopes)
            if response and "access_token" in response:
                token = str(response["access_token"])  # type: ignore[assignment]
                logger.debug("Successfully acquired token interactively")
            elif response and "error" in response:
                logger.error(
                    "Interactive token acquisition failed: %s - %s",
                    response.get("error"),
                    response.get("error_description"),
                )
        except Exception as ex:
            logger.error("Interactive token acquisition failed with exception: %s", ex)
            raise ServiceException(f"Failed to acquire authentication token: {ex}") from ex

    if not token:
        raise ServiceException("Authentication token cannot be acquired.")

    return token
