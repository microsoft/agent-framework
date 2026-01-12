# Copyright (c) Microsoft. All rights reserved.

"""AG-UI protocol integration for Agent Framework."""

import importlib.metadata

from ._agent import AgentFrameworkAgent
from ._client import AGUIChatClient
from ._confirmation_strategies import (
    ConfirmationStrategy,
    DefaultConfirmationStrategy,
    DocumentWriterConfirmationStrategy,
    RecipeConfirmationStrategy,
    TaskPlannerConfirmationStrategy,
)
from ._endpoint import add_agent_framework_fastapi_endpoint
from ._event_converters import AGUIEventConverter
from ._http_service import AGUIHttpService
from ._types import AGUIRequest

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

# Default OpenAPI tags for AG-UI endpoints
DEFAULT_TAGS = ["AG-UI"]

__all__ = [
    "AgentFrameworkAgent",
    "add_agent_framework_fastapi_endpoint",
    "AGUIChatClient",
    "AGUIEventConverter",
    "AGUIHttpService",
    "AGUIRequest",
    "ConfirmationStrategy",
    "DefaultConfirmationStrategy",
    "TaskPlannerConfirmationStrategy",
    "RecipeConfirmationStrategy",
    "DocumentWriterConfirmationStrategy",
    "DEFAULT_TAGS",
    "__version__",
]
