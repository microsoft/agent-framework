# Copyright (c) Microsoft. All rights reserved.

"""Microsoft Entra (Azure AD) identity channel for :mod:`agent_framework_hosting`."""

from ._channel import (
    EntraIdentityLinkChannel,
    EntraIdentityStore,
    entra_isolation_key,
)

__all__ = [
    "EntraIdentityLinkChannel",
    "EntraIdentityStore",
    "entra_isolation_key",
]
