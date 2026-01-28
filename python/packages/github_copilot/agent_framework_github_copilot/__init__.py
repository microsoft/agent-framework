# Copyright (c) Microsoft. All rights reserved.

import importlib.metadata

from ._agent import GithubCopilotAgent, GithubCopilotOptions
from ._settings import GithubCopilotSettings

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "GithubCopilotAgent",
    "GithubCopilotOptions",
    "GithubCopilotSettings",
    "__version__",
]
