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


from ._file_search import FileSearchBackend, FoundryFileSearchBackend, OpenAIFileSearchBackend


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
    """Configuration for uploading CU-extracted content to a vector store.

    When provided to ``ContentUnderstandingContextProvider``, analyzed document
    markdown is automatically uploaded to a vector store and a ``file_search``
    tool is registered on the context. This enables token-efficient RAG retrieval
    on follow-up turns for large documents.

    Use the factory methods ``from_openai`` or ``from_foundry`` for convenience,
    or pass a ``FileSearchBackend`` instance directly.

    Args:
        backend: A ``FileSearchBackend`` that handles vector store operations
            and produces the correct ``file_search`` tool format for the LLM client.
        vector_store_id: An existing vector store ID to use instead of
            auto-creating one. When provided, the provider uploads files to this
            store but does **not** delete it on close (the caller owns its lifecycle).
            When ``None`` (default), a new ephemeral vector store is created
            automatically and cleaned up on close.
    """

    backend: FileSearchBackend
    vector_store_id: str | None = None

    @staticmethod
    def from_openai(client: Any, *, vector_store_id: str | None = None) -> FileSearchConfig:
        """Create a config for OpenAI Responses API (``OpenAIChatClient``).

        Args:
            client: An ``AsyncOpenAI`` or ``AsyncAzureOpenAI`` client.
            vector_store_id: Optional existing vector store ID.
        """
        return FileSearchConfig(
            backend=OpenAIFileSearchBackend(client),
            vector_store_id=vector_store_id,
        )

    @staticmethod
    def from_foundry(client: Any, *, vector_store_id: str | None = None) -> FileSearchConfig:
        """Create a config for Azure AI Foundry (``FoundryChatClient``).

        Args:
            client: The OpenAI-compatible client from ``FoundryChatClient.client``.
            vector_store_id: Optional existing vector store ID.
        """
        return FileSearchConfig(
            backend=FoundryFileSearchBackend(client),
            vector_store_id=vector_store_id,
        )
