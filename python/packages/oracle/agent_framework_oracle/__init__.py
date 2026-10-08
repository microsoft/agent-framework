# Copyright (c) Microsoft. All rights reserved.

"""Oracle Database 23ai native-vector collections and stores."""

from __future__ import annotations

import importlib.metadata

from ._vector_store import OracleCollection, OracleSettings, OracleStore

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = ["OracleCollection", "OracleSettings", "OracleStore", "__version__"]
