# Copyright (c) Microsoft. All rights reserved.

"""Twelve Labs Pegasus and Marengo integration for Microsoft Agent Framework."""

from ._agent import VideoProcessingAgent
from ._client import TwelveLabsClient, TwelveLabsSettings
from ._exceptions import (
    AuthenticationError,
    FileTooLargeError,
    InvalidFormatError,
    ProcessingFailedError,
    RateLimitError,
    TwelveLabsError,
    UploadTimeoutError,
    VideoNotFoundError,
    VideoNotReadyError,
    VideoProcessingError,
    VideoUploadError,
)
from ._executor import BatchVideoExecutor, VideoExecutor
from ._middleware import VideoUploadProgressMiddleware
from ._tools import TwelveLabsTools
from ._types import (
    ChapterInfo,
    ChapterResult,
    HighlightInfo,
    HighlightResult,
    SearchResult,
    SearchResults,
    SummaryResult,
    VideoMetadata,
    VideoOperationType,
    VideoStatus,
)

__version__ = "0.1.0"

__all__ = [
    # Main classes
    "VideoProcessingAgent",
    "TwelveLabsClient",
    "TwelveLabsSettings",
    "TwelveLabsTools",
    "VideoExecutor",
    "BatchVideoExecutor",
    "VideoUploadProgressMiddleware",
    # Types
    "VideoMetadata",
    "VideoStatus",
    "VideoOperationType",
    "SummaryResult",
    "ChapterResult",
    "ChapterInfo",
    "HighlightResult",
    "HighlightInfo",
    "SearchResult",
    "SearchResults",
    # Exceptions
    "TwelveLabsError",
    "VideoUploadError",
    "FileTooLargeError",
    "InvalidFormatError",
    "UploadTimeoutError",
    "VideoProcessingError",
    "VideoNotReadyError",
    "ProcessingFailedError",
    "VideoNotFoundError",
    "RateLimitError",
    "AuthenticationError",
]
