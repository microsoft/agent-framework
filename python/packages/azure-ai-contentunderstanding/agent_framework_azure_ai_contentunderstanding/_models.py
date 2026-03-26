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
    """Configuration for uploading CU-extracted content to an existing vector store.

    When provided to ``ContentUnderstandingContextProvider``, analyzed document
    markdown is automatically uploaded to the specified vector store and the
    given ``file_search`` tool is registered on the context. This enables
    token-efficient RAG retrieval on follow-up turns for large documents.

    The caller is responsible for creating and managing the vector store and
    the ``file_search`` tool. Use :meth:`from_openai` or :meth:`from_foundry`
    factory methods for convenience.

    Args:
        backend: A ``FileSearchBackend`` that handles file upload/delete
            operations for the target vector store.
        vector_store_id: The ID of a pre-existing vector store to upload to.
        file_search_tool: A ``file_search`` tool object created via the LLM
            client's ``get_file_search_tool()`` factory method. This is
            registered on the context via ``extend_tools`` so the LLM can
            retrieve uploaded content.
    """

    backend: FileSearchBackend
    vector_store_id: str
    file_search_tool: Any

    @staticmethod
    def from_openai(
        client: Any,
        *,
        vector_store_id: str,
        file_search_tool: Any,
    ) -> FileSearchConfig:
        """Create a config for OpenAI Responses API (``OpenAIChatClient``).

        Args:
            client: An ``AsyncOpenAI`` or ``AsyncAzureOpenAI`` client.
            vector_store_id: The ID of the vector store to upload to.
            file_search_tool: Tool from ``OpenAIChatClient.get_file_search_tool()``.
        """
        return FileSearchConfig(
            backend=OpenAIFileSearchBackend(client),
            vector_store_id=vector_store_id,
            file_search_tool=file_search_tool,
        )

    @staticmethod
    def from_foundry(
        client: Any,
        *,
        vector_store_id: str,
        file_search_tool: Any,
    ) -> FileSearchConfig:
        """Create a config for Azure AI Foundry (``FoundryChatClient``).

        Args:
            client: The OpenAI-compatible client from ``FoundryChatClient.client``.
            vector_store_id: The ID of the vector store to upload to.
            file_search_tool: Tool from ``FoundryChatClient.get_file_search_tool()``.
        """
        return FileSearchConfig(
            backend=FoundryFileSearchBackend(client),
            vector_store_id=vector_store_id,
            file_search_tool=file_search_tool,
        )
