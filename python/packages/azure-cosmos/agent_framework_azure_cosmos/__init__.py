# Copyright (c) Microsoft. All rights reserved.

"""Azure Cosmos DB provider exports.

Supported classes:
    - ``CosmosContextProvider``
    - ``CosmosCheckpointStorage``
    - ``CosmosContextSearchMode``
    - ``CosmosHistoryProvider``
"""

import importlib.metadata

from ._checkpoint_storage import CosmosCheckpointStorage
from ._context_provider import CosmosContextProvider, CosmosContextSearchMode
from ._history_provider import CosmosHistoryProvider

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode

__all__ = [
    "CosmosCheckpointStorage",
    "CosmosContextProvider",
    "CosmosContextSearchMode",
    "CosmosHistoryProvider",
    "__version__",
]
