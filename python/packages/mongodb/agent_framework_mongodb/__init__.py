# Copyright (c) Microsoft. All rights reserved.

"""Async MongoDB vector collections and stores."""

from __future__ import annotations

import importlib.metadata

from ._vector_store import MongoDBCollection, MongoDBSettings, MongoDBStore

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = ["MongoDBCollection", "MongoDBSettings", "MongoDBStore", "__version__"]
