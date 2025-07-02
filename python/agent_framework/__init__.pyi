# Copyright (c) Microsoft. All rights reserved.

import importlib.metadata

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode
from ._logging import get_logger

__all__ = ["__version__", "get_logger"]
