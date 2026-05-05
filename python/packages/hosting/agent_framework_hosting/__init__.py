# Copyright (c) Microsoft. All rights reserved.

"""Multi-channel hosting for Microsoft Agent Framework agents.

Serve a single agent target through one or more **channels** — pluggable
adapters that expose the target over different transports such as the
OpenAI Responses API, Microsoft Teams, Telegram, and others. The base
package contains only the channel-neutral plumbing; concrete channels
ship in their own packages (``agent-framework-hosting-responses``,
``agent-framework-hosting-telegram``, …) so users install only what
they need.
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
from ._types import (
    Channel,
    ChannelCommand,
    ChannelCommandContext,
    ChannelContribution,
    ChannelIdentity,
    ChannelPush,
    ChannelRequest,
    ChannelRunHook,
    ChannelSession,
    ChannelStreamTransformHook,
    DeliveryReport,
    HostedRunResult,
    ResponseTarget,
    ResponseTargetKind,
    apply_run_hook,
)

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "ISOLATION_HEADER_CHAT",
    "ISOLATION_HEADER_USER",
    "AgentFrameworkHost",
    "Channel",
    "ChannelCommand",
    "ChannelCommandContext",
    "ChannelContext",
    "ChannelContribution",
    "ChannelIdentity",
    "ChannelPush",
    "ChannelRequest",
    "ChannelRunHook",
    "ChannelSession",
    "ChannelStreamTransformHook",
    "DeliveryReport",
    "HostedRunResult",
    "IsolationKeys",
    "ResponseTarget",
    "ResponseTargetKind",
    "__version__",
    "apply_run_hook",
    "get_current_isolation_keys",
    "logger",
    "reset_current_isolation_keys",
    "set_current_isolation_keys",
]
