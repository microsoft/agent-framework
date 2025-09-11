# Copyright (c) Microsoft. All rights reserved.

"""
Agent Framework Evaluation package.

This package provides tools for evaluating agents and workflows built using the Agent Framework.
It includes built-in benchmarks as well as utilities for running custom evaluations.

Each benchmark is implemented as a separate sub-module within the `agent_framework.eval` namespace.
"""

import importlib
import importlib.metadata

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode

__all__ = [
    "__version__",
]
