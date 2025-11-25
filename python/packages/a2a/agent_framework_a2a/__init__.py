# Copyright (c) Microsoft. All rights reserved.

import importlib.metadata

from ._a2a_executor import A2AExecutor
from ._agent import A2AAgent

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode

__all__ = [
    "A2AAgent",
    "A2AExecutor",
    "__version__",
]
