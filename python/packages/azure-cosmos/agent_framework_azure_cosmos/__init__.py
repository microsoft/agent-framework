# Copyright (c) Microsoft. All rights reserved.

import importlib
import importlib.metadata
from typing import TYPE_CHECKING, Any

from ._checkpoint_storage import CosmosCheckpointStorage
from ._history_provider import CosmosHistoryProvider

if TYPE_CHECKING:
    from ._vector_store import AzureCosmosSettings, CosmosCollection, CosmosStore

_VECTOR_EXPORTS = frozenset({"AzureCosmosSettings", "CosmosCollection", "CosmosStore"})

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode


def __getattr__(name: str) -> Any:
    if name not in _VECTOR_EXPORTS:
        raise AttributeError(f"Module {__name__!r} has no attribute {name!r}.")
    try:
        return getattr(importlib.import_module("._vector_store", __name__), name)
    except ImportError as exc:
        raise ImportError(
            "Azure Cosmos DB vector APIs require agent-framework-core with vector-store support."
        ) from exc


def __dir__() -> list[str]:
    return sorted((*globals(), *_VECTOR_EXPORTS))


__all__ = [
    "AzureCosmosSettings",
    "CosmosCheckpointStorage",
    "CosmosCollection",
    "CosmosHistoryProvider",
    "CosmosStore",
    "__version__",
]
