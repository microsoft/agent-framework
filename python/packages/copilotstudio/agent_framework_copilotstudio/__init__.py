# Copyright (c) Microsoft. All rights reserved.

import importlib.metadata

from ._acquire_token import acquire_token
from ._agent import CopilotStudioAgent

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode

__all__ = ["CopilotStudioAgent", "__version__", "acquire_token"]
