# Copyright (c) Microsoft. All rights reserved.

"""Per-request isolation keys for host/platform-provided request context.

``ChannelSession.isolation_key`` is the host's generic session partition key,
but different channels and platforms discover that key from different places:
protocol headers, request bodies, URL/path segments, webhook metadata, or
environment-provided context for ephemeral hosts.

This module covers the request-context case where a platform provides
isolation outside the channel payload. The Foundry Hosted Agents runtime, for
example, injects two well-known headers on requests it forwards to the user's
container:

* ``x-agent-user-isolation-key`` — opaque per-user partition key
* ``x-agent-chat-isolation-key`` — opaque per-conversation partition key

The generic host intentionally reuses those header names so the same isolation
context can be consumed by supporting providers. Reusing the names does **not**
mean ``agent-framework-hosting`` is a supported way to run on Foundry Hosted
Agents; use ``agent-framework-foundry-hosting`` for that hosting surface.

When those headers are present the host-installed ASGI middleware pushes them
into :data:`current_isolation_keys` for the duration of the request, then
resets it. Channels may still choose a different session key source and pass it
directly via ``ChannelSession(isolation_key=...)``.

The contextvar holds a plain :class:`IsolationKeys` mapping; conversion to
provider-specific types happens at the consuming provider so this module has no
provider dependencies.
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
    """Per-request isolation keys lifted from host/platform context."""

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
