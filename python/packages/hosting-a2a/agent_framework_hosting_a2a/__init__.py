# Copyright (c) Microsoft. All rights reserved.

"""A2A conversion helpers for app-owned Agent Framework hosting."""

import importlib.metadata

from ._conversion import a2a_from_run, a2a_to_run

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "__version__",
    "a2a_from_run",
    "a2a_to_run",
]
