# Copyright (c) Microsoft. All rights reserved.

"""Custom exceptions for Twelve Labs integration."""


class TwelveLabsError(Exception):
    """Base exception for all Twelve Labs integration errors."""

    pass


class VideoUploadError(TwelveLabsError):
    """Error during video upload."""

    pass


class FileTooLargeError(VideoUploadError):
    """File size exceeds maximum allowed."""

    pass


class InvalidFormatError(VideoUploadError):
    """Video format is not supported."""

    pass


class UploadTimeoutError(VideoUploadError):
    """Upload operation timed out."""

    pass


class VideoProcessingError(TwelveLabsError):
    """Error during video processing."""

    pass


class VideoNotReadyError(VideoProcessingError):
    """Video is not ready for the requested operation."""

    pass


class ProcessingFailedError(VideoProcessingError):
    """Video processing failed."""

    pass


class VideoNotFoundError(TwelveLabsError):
    """Requested video ID not found."""

    pass


class RateLimitError(TwelveLabsError):
    """API rate limit exceeded."""

    def __init__(self, message: str, retry_after: int = None):
        super().__init__(message)
        self.retry_after = retry_after


class AuthenticationError(TwelveLabsError):
    """Authentication with Twelve Labs API failed."""

    pass


class IndexError(TwelveLabsError):
    """Error related to video index operations."""

    pass


class InvalidParameterError(TwelveLabsError):
    """Invalid parameter provided to API."""

    pass


class NetworkError(TwelveLabsError):
    """Network-related error during API communication."""

    pass


class QuotaExceededError(TwelveLabsError):
    """Account quota exceeded."""

    pass
