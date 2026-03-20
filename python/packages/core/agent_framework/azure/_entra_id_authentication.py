# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Union

from azure.core.credentials import TokenCredential
from azure.core.credentials_async import AsyncTokenCredential

from ..exceptions import ChatClientInvalidAuthException

logger: logging.Logger = logging.getLogger(__name__)

AzureTokenProvider = Callable[[], Union[str, Awaitable[str]]]
"""A callable that returns a bearer token string, either synchronously or asynchronously."""

AzureCredentialTypes = Union[TokenCredential, AsyncTokenCredential]
"""Union of Azure credential types.

Accepts:
- ``TokenCredential`` — synchronous Azure credential (e.g. ``DefaultAzureCredential()``)
- ``AsyncTokenCredential`` — asynchronous Azure credential (e.g. ``azure.identity.aio.DefaultAzureCredential()``)
"""


def resolve_credential_to_token_provider(
    credential: AzureCredentialTypes | AzureTokenProvider,
    token_endpoint: str | None,
) -> AzureTokenProvider:
    """Convert an Azure credential or token provider into an ``ad_token_provider`` callable.

    If the credential is already a callable token provider, it is returned as-is
    (``token_endpoint`` is not required in this case).
    If it is a ``TokenCredential`` or ``AsyncTokenCredential``, it is wrapped using
    ``azure.identity.get_bearer_token_provider`` (sync or async variant) which
    handles token caching and automatic refresh.

    Args:
        credential: An Azure credential or token provider callable.
        token_endpoint: The token scope/endpoint
            (e.g. ``"https://cognitiveservices.azure.com/.default"``).
            Required when ``credential`` is a ``TokenCredential`` or ``AsyncTokenCredential``.

    Returns:
        A callable that returns a bearer token string (sync or async).

    Raises:
        ServiceInvalidAuthError: If the token endpoint is empty when needed for credential wrapping.
    """
    # Already a token provider callable (not a credential object) — use directly
    if callable(credential) and not isinstance(credential, (TokenCredential, AsyncTokenCredential)):
        return credential

    if not token_endpoint:
        raise ChatClientInvalidAuthException(
            "A token endpoint must be provided either in settings, as an environment variable, or as an argument."
        )

    if isinstance(credential, AsyncTokenCredential):
        from azure.identity.aio import get_bearer_token_provider as get_async_bearer_token_provider

        return get_async_bearer_token_provider(credential, token_endpoint)

    from azure.identity import get_bearer_token_provider

    return get_bearer_token_provider(credential, token_endpoint)  # type: ignore[arg-type]
