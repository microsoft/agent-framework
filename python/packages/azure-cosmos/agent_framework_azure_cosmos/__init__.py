# Copyright (c) Microsoft. All rights reserved.

import importlib.metadata

from ._checkpoint_storage import CosmosCheckpointStorage
from ._history_provider import CosmosHistoryProvider
from ._vector_store import AzureCosmosSettings, CosmosCollection, CosmosStore

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode

__all__ = [
    "AzureCosmosSettings",
    "CosmosCheckpointStorage",
    "CosmosCollection",
    "CosmosHistoryProvider",
    "CosmosStore",
    "__version__",
]
