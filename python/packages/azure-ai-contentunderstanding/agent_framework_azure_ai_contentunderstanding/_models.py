# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal, TypedDict


class AnalysisSection(str, Enum):
    """Selects which sections of the CU output to pass to the LLM."""

    MARKDOWN = "markdown"
    """Full document text with tables as HTML, reading order preserved."""

    FIELDS = "fields"
    """Extracted typed fields with confidence scores (when available)."""

    FIELD_GROUNDING = "field_grounding"
    """Page numbers and source locations for each extracted field."""

    TABLES = "tables"
    """Structured table data — already embedded in markdown."""

    PARAGRAPHS = "paragraphs"
    """Text segments with span offsets."""

    SECTIONS = "sections"
    """Document structural hierarchy."""


@dataclass
class ContentLimits:
    """Configurable limits to constrain input size for CU analysis.

    Defaults are stricter than CU service limits to keep analysis fast and
    output within LLM context windows.

    Args:
        max_pages: Maximum number of pages for PDF/TIFF/image documents.
        max_file_size_mb: Maximum file size in megabytes for all file types.
        max_audio_duration_s: Maximum audio duration in seconds.
        max_video_duration_s: Maximum video duration in seconds.
    """

    max_pages: int = 20
    """Maximum pages for PDF/TIFF/image documents. Not yet enforced — file size is checked instead."""

    max_file_size_mb: int = 10

    max_audio_duration_s: int = 300
    """Maximum audio duration in seconds. Not yet enforced — file size is checked instead."""

    max_video_duration_s: int = 120
    """Maximum video duration in seconds. Not yet enforced — file size is checked instead."""


class DocumentEntry(TypedDict):
    """Tracks the analysis state of a single document in session state."""

    status: Literal["pending", "ready", "failed"]
    filename: str
    media_type: str
    analyzer_id: str
    analyzed_at: str | None
    result: dict[str, object] | None
    error: str | None
