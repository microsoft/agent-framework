# Copyright (c) Microsoft. All rights reserved.

import importlib.metadata

from ._agent import ClaudeAgent, ClaudeAgentOptions
from ._settings import ClaudeAgentSettings

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode

__all__ = [
    "ClaudeAgent",
    "ClaudeAgentOptions",
    "ClaudeAgentSettings",
    "__version__",
]
