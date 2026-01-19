# Copyright (c) Microsoft. All rights reserved.

"""Local shell executor for Agent Framework."""

import importlib.metadata

from ._executor import LocalShellExecutor

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = ["LocalShellExecutor", "__version__"]
