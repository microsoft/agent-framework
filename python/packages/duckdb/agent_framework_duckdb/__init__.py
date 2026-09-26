# Copyright (c) Microsoft. All rights reserved.

"""DuckDB vector stores for Microsoft Agent Framework."""

import importlib.metadata

from ._vector_store import DuckDBCollection, DuckDBSettings, DuckDBStore

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = ["DuckDBCollection", "DuckDBSettings", "DuckDBStore", "__version__"]
