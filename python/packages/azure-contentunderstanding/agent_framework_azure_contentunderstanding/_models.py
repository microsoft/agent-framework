# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal, TypedDict

from ._file_search import FileSearchBackend, FoundryFileSearchBackend, OpenAIFileSearchBackend


class DocumentStatus(str, Enum):
    """Analysis lifecycle state of a tracked document."""

    ANALYZING = "analyzing"
    """CU analysis is in progress (deferred to background)."""

    UPLOADING = "uploading"
    """Analysis complete; vector store upload + indexing is in progress."""

    READY = "ready"
    """Analysis (and upload, if applicable) completed successfully."""

    FAILED = "failed"
    """Analysis or upload failed."""


AnalysisSection = Literal["markdown", "fields"]
"""Which sections of the CU output to pass to the LLM.

- ``"markdown"``: Full document text with tables as HTML, reading order preserved.
- ``"fields"``: Extracted typed fields with confidence scores (when available).
"""


class DocumentEntry(TypedDict):
    """Tracks the analysis state of a single document in session state."""

    status: DocumentStatus
    filename: str
    media_type: str
    analyzer_id: str
    analyzed_at: str | None
    analysis_duration_s: float | None
    upload_duration_s: float | None
    result: str | None
    """LLM-ready text rendered by ``azure.ai.contentunderstanding.to_llm_input``.

    Stored as a string (YAML front matter + markdown body) so every consumer
    (LLM context injection, vector store upload) can use it without re-rendering.
    ``None`` until analysis completes successfully.
    """
    search_payload: str | None
    """Optional alternate rendering used for ``file_search`` vector store uploads.

    Populated only when ``FileSearchConfig`` is configured. By default the
    payload omits structured fields (``include_fields=False``) for cleaner
    chunking; the caller can opt back into fields via
    ``FileSearchConfig.include_fields=True``.
    """
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
        include_fields: Whether the vector store upload payload should include
            CU-extracted structured fields. Defaults to ``False`` for cleaner
            text chunking. Set to ``True`` to include the same YAML field
            block that is sent to the LLM context.
    """

    backend: FileSearchBackend
    vector_store_id: str
    file_search_tool: Any
    include_fields: bool = False

    @staticmethod
    def from_openai(
        client: Any,
        *,
        vector_store_id: str,
        file_search_tool: Any,
        include_fields: bool = False,
    ) -> FileSearchConfig:
        """Create a config for OpenAI Responses API (``OpenAIChatClient``).

        Args:
            client: An ``AsyncOpenAI`` or ``AsyncAzureOpenAI`` client.
            vector_store_id: The ID of the vector store to upload to.
            file_search_tool: Tool from ``OpenAIChatClient.get_file_search_tool()``.
            include_fields: Whether to include CU-extracted fields in the upload
                payload. Defaults to ``False``.
        """
        return FileSearchConfig(
            backend=OpenAIFileSearchBackend(client),
            vector_store_id=vector_store_id,
            file_search_tool=file_search_tool,
            include_fields=include_fields,
        )

    @staticmethod
    def from_foundry(
        client: Any,
        *,
        vector_store_id: str,
        file_search_tool: Any,
        include_fields: bool = False,
    ) -> FileSearchConfig:
        """Create a config for Azure AI Foundry (``FoundryChatClient``).

        Args:
            client: The OpenAI-compatible client from ``FoundryChatClient.client``.
            vector_store_id: The ID of the vector store to upload to.
            file_search_tool: Tool from ``FoundryChatClient.get_file_search_tool()``.
            include_fields: Whether to include CU-extracted fields in the upload
                payload. Defaults to ``False``.
        """
        return FileSearchConfig(
            backend=FoundryFileSearchBackend(client),
            vector_store_id=vector_store_id,
            file_search_tool=file_search_tool,
            include_fields=include_fields,
        )
