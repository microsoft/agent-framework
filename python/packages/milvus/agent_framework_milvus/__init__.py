# Copyright (c) Microsoft. All rights reserved.

"""Milvus vector stores for Microsoft Agent Framework."""

import importlib.metadata

from ._vector_store import MilvusCollection, MilvusSettings, MilvusStore

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = ["MilvusCollection", "MilvusSettings", "MilvusStore", "__version__"]
