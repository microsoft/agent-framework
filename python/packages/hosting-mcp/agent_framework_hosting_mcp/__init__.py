# Copyright (c) Microsoft. All rights reserved.

"""Agent and workflow MCP tool adapters for app-owned hosting."""

import importlib.metadata

from ._agent_tool import MCPAgentTool
from ._conversion import mcp_from_run, mcp_to_run
from ._workflow_tool import MCPWorkflowTool

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "MCPAgentTool",
    "MCPWorkflowTool",
    "__version__",
    "mcp_from_run",
    "mcp_to_run",
]
