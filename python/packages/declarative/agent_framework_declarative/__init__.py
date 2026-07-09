# Copyright (c) Microsoft. All rights reserved.

"""Declarative specification support for Microsoft Agent Framework.

Release stage:

* The declarative-workflows surface (``WorkflowFactory``, executors, handlers,
  etc.) is at release-candidate stability.
* The declarative-agents surface (``AgentFactory`` and the YAML agent
  loading/parsing path: ``DeclarativeLoaderError``, ``ProviderLookupError``,
  ``ProviderTypeMapping``) is *experimental* and may change or be removed in
  future versions without notice. Using these symbols emits an
  ``ExperimentalWarning`` on first use.
"""

from importlib import metadata

from ._loader import AgentFactory, DeclarativeLoaderError, ProviderLookupError, ProviderTypeMapping
from ._workflows import (
    AgentExternalInputRequest,
    AgentExternalInputResponse,
    DeclarativeActionError,
    DeclarativeWorkflowError,
    DefaultHttpRequestHandler,
    DefaultMCPToolHandler,
    ExternalInputRequest,
    ExternalInputResponse,
    HttpRequestHandler,
    HttpRequestInfo,
    HttpRequestResult,
    MCPToolApprovalRequest,
    MCPToolHandler,
    MCPToolInvocation,
    MCPToolResult,
    ToolApprovalRequest,
    ToolApprovalResponse,
    WorkflowFactory,
    WorkflowState,
)

try:
    __version__ = metadata.version(__name__)
except metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode

__all__ = [
    "AgentExternalInputRequest",
    "AgentExternalInputResponse",
    "AgentFactory",
    "DeclarativeActionError",
    "DeclarativeLoaderError",
    "DeclarativeWorkflowError",
    "DefaultHttpRequestHandler",
    "DefaultMCPToolHandler",
    "ExternalInputRequest",
    "ExternalInputResponse",
    "HttpRequestHandler",
    "HttpRequestInfo",
    "HttpRequestResult",
    "MCPToolApprovalRequest",
    "MCPToolHandler",
    "MCPToolInvocation",
    "MCPToolResult",
    "ProviderLookupError",
    "ProviderTypeMapping",
    "ToolApprovalRequest",
    "ToolApprovalResponse",
    "WorkflowFactory",
    "WorkflowState",
    "__version__",
]
