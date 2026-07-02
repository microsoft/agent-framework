# Copyright (c) Microsoft. All rights reserved.

"""Multi-channel hosting for Microsoft Agent Framework agents.

Serve a single agent target through one or more **channels** — pluggable
adapters that expose the target over different transports. The base
package contains only the channel-neutral plumbing; concrete channels
ship in their own packages, such as ``agent-framework-hosting-responses``,
so users install only what they need.
"""

import importlib.metadata

from ._host import AgentFrameworkHost, ChannelContext, logger
from ._isolation import (
    ISOLATION_HEADER_CHAT,
    ISOLATION_HEADER_USER,
    IsolationKeys,
    get_current_isolation_keys,
    reset_current_isolation_keys,
    set_current_isolation_keys,
)
from ._state import AgentFrameworkState, AgentRunArgs, SessionStore, WorkflowRunArgs
from ._types import (
    Channel,
    ChannelCommand,
    ChannelCommandContext,
    ChannelContribution,
    ChannelIdentity,
    ChannelRequest,
    ChannelResponseHook,
    ChannelRunHook,
    ChannelSession,
    ChannelStreamUpdateHook,
    HostedRunResult,
    HostStatePaths,
)

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "ISOLATION_HEADER_CHAT",
    "ISOLATION_HEADER_USER",
    "AgentFrameworkHost",
    "AgentFrameworkState",
    "AgentRunArgs",
    "Channel",
    "ChannelCommand",
    "ChannelCommandContext",
    "ChannelContext",
    "ChannelContribution",
    "ChannelIdentity",
    "ChannelRequest",
    "ChannelResponseHook",
    "ChannelRunHook",
    "ChannelSession",
    "ChannelStreamUpdateHook",
    "HostStatePaths",
    "HostedRunResult",
    "IsolationKeys",
    "SessionStore",
    "WorkflowRunArgs",
    "__version__",
    "get_current_isolation_keys",
    "logger",
    "reset_current_isolation_keys",
    "set_current_isolation_keys",
]
