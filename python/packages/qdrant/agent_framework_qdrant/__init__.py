# Copyright (c) Microsoft. All rights reserved.

"""Qdrant vector stores for Microsoft Agent Framework."""

import importlib.metadata

from ._vector_store import QdrantCollection, QdrantSettings, QdrantStore

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = ["QdrantCollection", "QdrantSettings", "QdrantStore", "__version__"]
