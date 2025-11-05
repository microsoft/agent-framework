# Copyright (c) Microsoft. All rights reserved.

"""AG-UI protocol integration for Agent Framework."""

import importlib.metadata

from ._agent import AgentFrameworkAgent
from ._confirmation_strategies import (
    ConfirmationStrategy,
    DefaultConfirmationStrategy,
    DocumentWriterConfirmationStrategy,
    RecipeConfirmationStrategy,
    TaskPlannerConfirmationStrategy,
)
from ._endpoint import add_agent_framework_fastapi_endpoint

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "AgentFrameworkAgent",
    "add_agent_framework_fastapi_endpoint",
    "ConfirmationStrategy",
    "DefaultConfirmationStrategy",
    "TaskPlannerConfirmationStrategy",
    "RecipeConfirmationStrategy",
    "DocumentWriterConfirmationStrategy",
    "__version__",
]
