# Copyright (c) Microsoft. All rights reserved.

from importlib import metadata

from ._loader import AgentFactory, DeclarativeLoaderError, ProviderLookupError, ProviderTypeMapping
from ._workflows import (
    AgentExternalInputRequest,
    AgentExternalInputResponse,
    DeclarativeActionError,
    DeclarativeWorkflowError,
    DefaultHttpRequestHandler,
    ExternalInputRequest,
    ExternalInputResponse,
    HttpRequestHandler,
    HttpRequestInfo,
    HttpRequestResult,
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
    "ExternalInputRequest",
    "ExternalInputResponse",
    "HttpRequestHandler",
    "HttpRequestInfo",
    "HttpRequestResult",
    "ProviderLookupError",
    "ProviderTypeMapping",
    "WorkflowFactory",
    "WorkflowState",
    "__version__",
]
