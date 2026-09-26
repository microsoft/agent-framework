# Copyright (c) Microsoft. All rights reserved.

"""SQL Server native vector collections and stores for Agent Framework."""

from __future__ import annotations

import importlib.metadata

from ._vector_store import SqlServerCollection, SqlServerCommittedCleanupException, SqlServerSettings, SqlServerStore

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "SqlServerCollection",
    "SqlServerCommittedCleanupException",
    "SqlServerSettings",
    "SqlServerStore",
    "__version__",
]
