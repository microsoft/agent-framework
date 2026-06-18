# Copyright (c) Microsoft. All rights reserved.

import importlib.metadata
import os

# Disable Mem0 telemetry by default to prevent usage data from being sent to telemetry provider.
# Users can opt-in by setting MEM0_TELEMETRY=true before importing this package.
if os.environ.get("MEM0_TELEMETRY") is None:
    os.environ["MEM0_TELEMETRY"] = "false"

from ._context_provider import Mem0ContextProvider

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode

__all__ = [
    "Mem0ContextProvider",
    "__version__",
]
