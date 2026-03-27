# Copyright (c) Microsoft. All rights reserved.

"""File search backend abstraction for vector store file operations.

Provides a unified interface for uploading CU-extracted content to
vector stores across different LLM clients. Two implementations:

- ``OpenAIFileSearchBackend`` — for ``OpenAIChatClient`` (Responses API)
- ``FoundryFileSearchBackend`` — for ``FoundryChatClient`` (Responses API via Azure)

Both share the same OpenAI-compatible vector store file API but differ
in the file upload ``purpose`` value.

Vector store creation, tool construction, and lifecycle management are
the caller's responsibility — the backend only handles file upload/delete.
"""

from __future__ import annotations

import io
from abc import ABC, abstractmethod
from typing import Any


class FileSearchBackend(ABC):
    """Abstract interface for vector store file operations.

    Implementations handle the differences between OpenAI and Foundry
    file upload APIs (e.g., different ``purpose`` values).

    Vector store creation, deletion, and ``file_search`` tool construction
    are **not** part of this interface — those are managed by the caller.
    """

    @abstractmethod
    async def upload_file(self, vector_store_id: str, filename: str, content: bytes) -> str:
        """Upload a file to a vector store and return the file ID."""

    @abstractmethod
    async def delete_file(self, file_id: str) -> None:
        """Delete a previously uploaded file by ID."""


class _OpenAICompatBackend(FileSearchBackend):
    """Shared base for OpenAI-compatible file upload backends.

    Both OpenAI and Foundry use the same ``client.files.*`` and
    ``client.vector_stores.files.*`` API surface. Subclasses only
    override the file upload ``purpose``.
    """

    _FILE_PURPOSE: str  # Subclasses must set this

    def __init__(self, client: Any) -> None:
        self._client = client

    async def upload_file(self, vector_store_id: str, filename: str, content: bytes) -> str:
        uploaded = await self._client.files.create(
            file=(filename, io.BytesIO(content)),
            purpose=self._FILE_PURPOSE,
        )
        # Use create_and_poll to wait for indexing to complete before returning.
        # Without this, file_search queries may return no results immediately
        # after upload because the vector store index isn't ready yet.
        await self._client.vector_stores.files.create_and_poll(
            vector_store_id=vector_store_id,
            file_id=uploaded.id,
        )
        return uploaded.id  # type: ignore[no-any-return]

    async def delete_file(self, file_id: str) -> None:
        await self._client.files.delete(file_id)


class OpenAIFileSearchBackend(_OpenAICompatBackend):
    """File search backend for OpenAI Responses API.

    Use with ``OpenAIChatClient`` or ``AzureOpenAIResponsesClient``.
    Requires an ``AsyncOpenAI`` or ``AsyncAzureOpenAI`` client.

    Args:
        client: An async OpenAI client (``AsyncOpenAI`` or ``AsyncAzureOpenAI``)
            that supports ``client.files.*`` and ``client.vector_stores.*`` APIs.
    """

    _FILE_PURPOSE = "user_data"


class FoundryFileSearchBackend(_OpenAICompatBackend):
    """File search backend for Azure AI Foundry.

    Use with ``FoundryChatClient``. Requires the OpenAI-compatible client
    obtained from ``FoundryChatClient.client`` (i.e.,
    ``project_client.get_openai_client()``).

    Args:
        client: The OpenAI-compatible async client from a ``FoundryChatClient``
            (access via ``foundry_client.client``).
    """

    _FILE_PURPOSE = "assistants"
