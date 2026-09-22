# Copyright (c) Microsoft. All rights reserved.

"""Async PostgreSQL vector storage and durable agent memory."""

from __future__ import annotations

import importlib.metadata

from ._checkpoint_storage import PostgresCheckpointStorage
from ._memory_client import PostgresMemoryClient
from ._memory_context_provider import PostgresMemoryContextProvider
from ._memory_types import (
    PostgresMemoryClientOptions,
    PostgresMemoryContextProviderState,
    PostgresMemoryPromptOptions,
    PostgresMemoryRecord,
    PostgresMemoryScope,
    PostgresMemoryType,
    PostgresMemoryVectorIndexKind,
)
from ._vector_store import PostgresCollection, PostgresSettings, PostgresStore

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "PostgresCheckpointStorage",
    "PostgresCollection",
    "PostgresMemoryClient",
    "PostgresMemoryClientOptions",
    "PostgresMemoryContextProvider",
    "PostgresMemoryContextProviderState",
    "PostgresMemoryPromptOptions",
    "PostgresMemoryRecord",
    "PostgresMemoryScope",
    "PostgresMemoryType",
    "PostgresMemoryVectorIndexKind",
    "PostgresSettings",
    "PostgresStore",
    "__version__",
]
