# Copyright (c) Microsoft. All rights reserved.

"""Constants for Azure Content Understanding context provider.

Supported media types, MIME aliases, and analyzer mappings used by
the file detection and analysis pipeline.
"""

from __future__ import annotations

# MIME types used to match against the resolved media type for routing files to CU analysis.
# The media type may be provided via Content.media_type or inferred (e.g., via sniffing or filename)
# when missing or generic (such as application/octet-stream). Only files whose resolved media type is
# in this set will be processed; others are skipped.
#
# Supported input file types:
# https://learn.microsoft.com/azure/ai-services/content-understanding/service-limits#input-file-limits
SUPPORTED_MEDIA_TYPES: frozenset[str] = frozenset({
    # Documents and images
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/tiff",
    "image/bmp",
    "image/heif",
    "image/heic",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    # Text
    "text/plain",
    "text/html",
    "text/markdown",
    "text/rtf",
    "text/xml",
    "application/xml",
    "message/rfc822",
    "application/vnd.ms-outlook",
    # Audio
    "audio/wav",
    "audio/mpeg",
    "audio/mp3",
    "audio/mp4",
    "audio/m4a",
    "audio/flac",
    "audio/ogg",
    "audio/opus",
    "audio/webm",
    "audio/x-ms-wma",
    "audio/aac",
    "audio/amr",
    "audio/3gpp",
    # Video
    "video/mp4",
    "video/quicktime",
    "video/x-msvideo",
    "video/webm",
    "video/x-flv",
    "video/x-ms-wmv",
    "video/x-ms-asf",
    "video/x-matroska",
})

# Mapping from filetype's MIME output to our canonical SUPPORTED_MEDIA_TYPES values.
# filetype uses some x-prefixed variants that differ from our set.
MIME_ALIASES: dict[str, str] = {
    "audio/x-wav": "audio/wav",
    "audio/x-flac": "audio/flac",
    "video/x-m4v": "video/mp4",
}

# Mapping from media type prefix to the appropriate prebuilt CU analyzer.
# Used when analyzer_id is None (auto-detect mode).
MEDIA_TYPE_ANALYZER_MAP: dict[str, str] = {
    "audio/": "prebuilt-audioSearch",
    "video/": "prebuilt-videoSearch",
}
DEFAULT_ANALYZER: str = "prebuilt-documentSearch"
