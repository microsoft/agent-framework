# Copyright (c) Microsoft. All rights reserved.

"""Built-in tools for the Microsoft Agent Framework."""

from __future__ import annotations

import importlib.metadata

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = ["__version__"]
