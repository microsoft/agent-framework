# Copyright (c) Microsoft. All rights reserved.

import importlib.metadata

from ._context_provider import ContentUnderstandingContextProvider
from ._models import AnalysisSection, FileSearchConfig

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "AnalysisSection",
    "ContentUnderstandingContextProvider",
    "FileSearchConfig",
    "__version__",
]
