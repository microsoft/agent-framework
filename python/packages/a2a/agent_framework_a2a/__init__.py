# Copyright (c) Microsoft. All rights reserved.

import importlib.metadata

from ._a2a_event_adapter import A2aEventAdapter, BaseA2aEventAdapter
from ._a2a_execution_context import A2aExecutionContext
from ._a2a_executor import A2aExecutor
from ._agent import A2AAgent

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode

__all__ = [
    "A2AAgent",
    "A2aEventAdapter",
    "A2aExecutionContext",
    "A2aExecutor",
    "BaseA2aEventAdapter",
    "__version__",
]
