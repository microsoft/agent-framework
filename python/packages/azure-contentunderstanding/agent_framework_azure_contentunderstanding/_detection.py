# Copyright (c) Microsoft. All rights reserved.

"""File detection utilities for Azure Content Understanding context provider.

Functions for scanning input messages, sniffing MIME types, deriving
document keys, and extracting binary data from content items.
"""

from __future__ import annotations

import base64
import logging
import mimetypes
import re
import uuid

import filetype
from agent_framework import Content, SessionContext

logger = logging.getLogger("agent_framework.azure_contentunderstanding")

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


def detect_and_strip_files(
    context: SessionContext,
) -> list[tuple[str, Content, bytes | None]]:
    """Scan input messages for supported file content and prepare for CU analysis.

    Scans for type ``data`` or ``uri`` content supported by Azure Content
    Understanding, strips them from messages to prevent raw binary being sent
    to the LLM, and returns metadata for CU analysis.

    Detected files are tracked via ``doc_key`` (derived from filename, URL,
    or UUID) and their analysis status is managed in session state.

    When the upstream MIME type is unreliable (``application/octet-stream``
    or missing), binary content sniffing via ``filetype`` is used to
    determine the real media type, with ``mimetypes.guess_type`` as a
    filename-based fallback.

    Returns:
        List of (doc_key, content_item, binary_data) tuples for files to analyze.
    """
    results: list[tuple[str, Content, bytes | None]] = []
    strip_ids: set[int] = set()

    for msg in context.input_messages:
        for c in msg.contents:
            if c.type not in ("data", "uri"):
                continue

            media_type = c.media_type
            # Fast path: already a known supported type
            if media_type and media_type in SUPPORTED_MEDIA_TYPES:
                binary_data = extract_binary(c)
                results.append((derive_doc_key(c), c, binary_data))
                strip_ids.add(id(c))
                continue

            # Slow path: unreliable MIME — sniff binary content
            if (not media_type) or (media_type == "application/octet-stream"):
                binary_data = extract_binary(c)
                resolved = sniff_media_type(binary_data, c)
                if resolved and (resolved in SUPPORTED_MEDIA_TYPES):
                    c.media_type = resolved
                    results.append((derive_doc_key(c), c, binary_data))
                    strip_ids.add(id(c))

        # Strip detected files from input so raw binary isn't sent to LLM
        msg.contents = [c for c in msg.contents if id(c) not in strip_ids]

    return results


def sniff_media_type(binary_data: bytes | None, content: Content) -> str | None:
    """Sniff the actual MIME type from binary data, with filename fallback.

    Uses ``filetype`` (magic-bytes) first, then ``mimetypes.guess_type``
    on the filename. Normalizes filetype's variant MIME values (e.g.
    ``audio/x-wav`` -> ``audio/wav``) via ``MIME_ALIASES``.
    """
    # 1. Binary sniffing via filetype (needs only first 261 bytes)
    if binary_data:
        kind = filetype.guess(binary_data[:262])  # type: ignore[reportUnknownMemberType]
        if kind:
            mime: str = kind.mime  # type: ignore[reportUnknownMemberType]
            return MIME_ALIASES.get(mime, mime)

    # 2. Filename extension fallback — try additional_properties first,
    # then extract basename from external URL path
    filename: str | None = None
    if content.additional_properties:
        filename = content.additional_properties.get("filename")
    if not filename and content.uri and not content.uri.startswith("data:"):
        # Extract basename from URL path (e.g. "https://example.com/report.pdf?v=1" -> "report.pdf")
        filename = content.uri.split("?")[0].split("#")[0].rsplit("/", 1)[-1]
    if filename:
        guessed, _ = mimetypes.guess_type(filename)  # uses file extension to guess MIME type
        if guessed:
            return MIME_ALIASES.get(guessed, guessed)

    return None


def is_supported_content(content: Content) -> bool:
    """Check if a content item is a supported file type for CU analysis."""
    if content.type not in ("data", "uri"):
        return False
    media_type = content.media_type
    if not media_type:
        return False
    return media_type in SUPPORTED_MEDIA_TYPES


def sanitize_doc_key(raw: str) -> str:
    """Sanitize a document key to prevent prompt injection.

    Removes control characters (newlines, tabs, etc.), collapses
    whitespace, strips surrounding whitespace, and caps length at
    255 characters.
    """
    # Remove control characters (C0/C1 controls, including \n, \r, \t)
    cleaned = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", raw)
    # Collapse whitespace
    cleaned = " ".join(cleaned.split())
    # Cap length
    return cleaned[:255] if cleaned else f"doc_{uuid.uuid4().hex[:8]}"


def derive_doc_key(content: Content) -> str:
    """Derive a unique document key from content metadata.

    The key is used to track documents in session state. Duplicate keys
    within a session are rejected (not re-analyzed) to prevent orphaned
    vector store entries.

    The returned key is sanitized to prevent prompt injection via
    crafted filenames (control characters removed, length capped).

    Priority: filename > URL basename > generated UUID.
    """
    # 1. Filename from additional_properties
    if content.additional_properties:
        filename = content.additional_properties.get("filename")
        if filename and isinstance(filename, str):
            return sanitize_doc_key(filename)

    # 2. URL path basename for external URIs (e.g. "https://example.com/report.pdf" -> "report.pdf")
    if content.type == "uri" and content.uri and not content.uri.startswith("data:"):
        path = content.uri.split("?")[0].split("#")[0]  # strip query params and fragments
        # rstrip("/") handles trailing slashes (e.g. ".../files/" -> ".../files")
        # rsplit("/", 1)[-1] splits from the right once to get the last path segment
        basename = path.rstrip("/").rsplit("/", 1)[-1]
        if basename:
            return sanitize_doc_key(basename)

    # 3. Fallback: generate a unique ID for anonymous uploads (no filename, no URL)
    return f"doc_{uuid.uuid4().hex[:8]}"


def extract_binary(content: Content) -> bytes | None:
    """Extract binary data from a data URI content item.

    Only handles ``data:`` URIs (base64-encoded). Returns ``None`` for
    external URLs -- those are passed directly to CU via ``begin_analyze``.
    """
    if content.uri and content.uri.startswith("data:"):
        try:
            _, data_part = content.uri.split(",", 1)
            return base64.b64decode(data_part)
        except Exception:
            logger.warning("Failed to decode base64 data URI")
            return None
    return None
