# Copyright (c) Microsoft. All rights reserved.

"""Azure Content Understanding integration for Microsoft Agent Framework.

Provides a context provider that analyzes file attachments (documents, images,
audio, video) using Azure Content Understanding and injects structured results
into the LLM context.
"""

import importlib.metadata

from ._context_provider import ContentUnderstandingContextProvider
from ._file_search import FileSearchBackend
from ._models import AnalysisSection, DocumentStatus, FileSearchConfig

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "AnalysisSection",
    "ContentUnderstandingContextProvider",
    "DocumentStatus",
    "FileSearchBackend",
    "FileSearchConfig",
    "__version__",
]
