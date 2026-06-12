# Copyright (c) Microsoft. All rights reserved.

"""Model Context Protocol (MCP) tool channel for :mod:`agent_framework_hosting`.

Exposes the hosted target (an ``Agent`` or a ``Workflow``) as a single MCP
tool over the Streamable-HTTP transport so MCP clients — other agents, IDE
tooling — can invoke it. Routes through the host pipeline, so sessions,
request metadata, and hooks apply.
"""

import importlib.metadata

from ._channel import MCPChannel

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "MCPChannel",
    "__version__",
]
