# Copyright (c) Microsoft. All rights reserved.

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
