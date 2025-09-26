# Copyright (c) Microsoft. All rights reserved.

"""
RL Module for Microsoft Agent Framework
"""

# ruff: noqa: F403

import importlib.metadata

from agentlightning import *  # type: ignore

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode
