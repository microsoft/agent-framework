# Copyright (c) Microsoft. All rights reserved.

"""Per-request isolation keys read from inbound HTTP headers.

The Foundry Hosted Agents runtime injects two well-known headers on every
request it forwards to the user's container:

* ``x-agent-user-isolation-key`` — opaque per-user partition key
* ``x-agent-chat-isolation-key`` — opaque per-conversation partition key

When the headers are present we are running inside (or being driven by) the
Foundry runtime; when they are absent we are running in plain local dev. The
host installs an ASGI middleware in :meth:`AgentFrameworkHost._build_app`
that reads both headers off every inbound HTTP request and pushes them into
the :data:`current_isolation_keys` contextvar for the duration of the
request, then resets it. Providers that need partition-aware storage (most
notably ``FoundryHostedAgentHistoryProvider``) read the contextvar via
:func:`get_current_isolation_keys` and apply the keys to their backend
calls — so app authors don't have to wire any middleware themselves and
channels stay free of Foundry-specific header knowledge.

The contextvar holds a plain :class:`IsolationKeys` mapping; conversion to
provider-specific types (e.g. Foundry's ``IsolationContext``) happens at
the consuming provider so this module has no provider dependencies.
"""

from __future__ import annotations

from contextvars import ContextVar, Token

__all__ = [
    "ISOLATION_HEADER_CHAT",
    "ISOLATION_HEADER_USER",
    "IsolationKeys",
    "current_isolation_keys",
    "get_current_isolation_keys",
    "reset_current_isolation_keys",
    "set_current_isolation_keys",
]


ISOLATION_HEADER_USER = "x-agent-user-isolation-key"
ISOLATION_HEADER_CHAT = "x-agent-chat-isolation-key"


class IsolationKeys:
    """Per-request Foundry isolation keys lifted off the inbound headers."""

    def __init__(self, user_key: str | None = None, chat_key: str | None = None) -> None:
        self.user_key = user_key
        self.chat_key = chat_key

    @property
    def is_empty(self) -> bool:
        return self.user_key is None and self.chat_key is None


current_isolation_keys: ContextVar[IsolationKeys | None] = ContextVar(
    "agent_framework_hosting_isolation_keys",
    default=None,
)


def get_current_isolation_keys() -> IsolationKeys | None:
    """Return the isolation keys bound to the current request, if any."""
    return current_isolation_keys.get()


def set_current_isolation_keys(keys: IsolationKeys | None) -> Token[IsolationKeys | None]:
    """Bind ``keys`` to the current async context and return a reset token."""
    return current_isolation_keys.set(keys)


def reset_current_isolation_keys(token: Token[IsolationKeys | None]) -> None:
    """Restore the isolation contextvar to its prior value."""
    current_isolation_keys.reset(token)
