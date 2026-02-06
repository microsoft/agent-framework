# Copyright (c) Microsoft. All rights reserved.

import importlib.metadata

from ._agent import GitHubCopilotAgent, GitHubCopilotOptions
from ._settings import GitHubCopilotSettings

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "GitHubCopilotAgent",
    "GitHubCopilotOptions",
    "GitHubCopilotSettings",
    "__version__",
]
