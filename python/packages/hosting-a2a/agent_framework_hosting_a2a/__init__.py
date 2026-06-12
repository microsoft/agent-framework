# Copyright (c) Microsoft. All rights reserved.

"""A2A (Agent-to-Agent) channel for :mod:`agent_framework_hosting`.

Exposes the hosted target (an ``Agent`` or a ``Workflow``) as an A2A peer agent
— publishing an agent card and JSON-RPC routes — while routing every request
through the host pipeline so sessions, request metadata, and hooks apply.
"""

import importlib.metadata

from ._channel import A2AChannel
from ._executor import HostAgentExecutor

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "A2AChannel",
    "HostAgentExecutor",
    "__version__",
]
