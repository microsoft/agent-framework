# Copyright (c) Microsoft. All rights reserved.

"""RL Module for Microsoft Agent Framework."""

# ruff: noqa: F403

import importlib.metadata

from agent_framework.observability import OBSERVABILITY_SETTINGS
from agentlightning import *  # type: ignore

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode


def init() -> None:
    """Initialize the agent-framework-lab-lightning for training."""
    OBSERVABILITY_SETTINGS.enable_otel = True


__all__: list[str] = ["init"]
