# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal, TypedDict


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


class DocumentEntry(TypedDict):
    """Tracks the analysis state of a single document in session state."""

    status: Literal["pending", "ready", "failed"]
    filename: str
    media_type: str
    analyzer_id: str
    analyzed_at: str | None
    result: dict[str, object] | None
    error: str | None


@dataclass
class FileSearchConfig:
    """Configuration for uploading CU-extracted content to an OpenAI vector store.

    When provided to ``ContentUnderstandingContextProvider``, analyzed document
    markdown is automatically uploaded to a vector store and a ``file_search``
    tool is registered on the context. This enables token-efficient RAG retrieval
    on follow-up turns for large documents.

    Args:
        openai_client: An async OpenAI client (``AsyncOpenAI`` or ``AsyncAzureOpenAI``)
            used to create files and vector stores. Must support
            ``client.files.create()`` and ``client.vector_stores.*`` APIs.
        vector_store_id: An existing OpenAI vector store ID to use instead of
            auto-creating one. When provided, the provider uploads files to this
            store but does **not** delete it on close (the caller owns its lifecycle).
            When ``None`` (default), a new ephemeral vector store is created
            automatically and cleaned up on close.
    """

    openai_client: Any
    vector_store_id: str | None = None
