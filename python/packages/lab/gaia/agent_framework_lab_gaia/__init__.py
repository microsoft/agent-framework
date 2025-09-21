# Copyright (c) Microsoft. All rights reserved.

"""
GAIA benchmark module for Agent Framework.
"""

import importlib.metadata

from ._types import Evaluation, Evaluator, Prediction, Task, TaskResult, TaskRunner
from .gaia import GAIA, GAIATelemetryConfig, gaia_scorer, viewer_main

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode

__all__ = [
    "GAIA",
    "GAIATelemetryConfig",
    "gaia_scorer",
    "viewer_main",
    "Task",
    "Prediction",
    "Evaluation",
    "TaskResult",
    "TaskRunner",
    "Evaluator",
]
