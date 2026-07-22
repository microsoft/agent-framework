# Copyright (c) Microsoft. All rights reserved.

"""Agent and workflow MCP tool adapters for app-owned hosting."""

import importlib.metadata

from ._agent_tool import AgentMCPTool
from ._conversion import mcp_from_run, mcp_to_run
from ._workflow_tool import WorkflowMCPTool

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "AgentMCPTool",
    "WorkflowMCPTool",
    "__version__",
    "mcp_from_run",
    "mcp_to_run",
]
