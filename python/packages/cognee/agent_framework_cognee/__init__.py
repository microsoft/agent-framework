# Copyright (c) Microsoft. All rights reserved.

import importlib.metadata

from ._tools import cognee_add, cognee_search, get_cognee_tools

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode

__all__ = [
    "__version__",
    "cognee_add",
    "cognee_search",
    "get_cognee_tools",
]
