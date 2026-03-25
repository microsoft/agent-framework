# Copyright (c) Microsoft. All rights reserved.

"""File search backend abstraction for vector store operations.

Provides a unified interface for uploading CU-extracted content to
vector stores and creating the correct ``file_search`` tool format
for different LLM clients. Two implementations are included:

- ``OpenAIFileSearchBackend`` — for ``OpenAIChatClient`` (Responses API)
- ``FoundryFileSearchBackend`` — for ``FoundryChatClient`` (Responses API via Azure)

Both share the same OpenAI-compatible vector store CRUD API but differ
in file upload ``purpose`` and the tool object format expected by each client.
"""

from __future__ import annotations

import io
import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger("agent_framework.azure_ai_contentunderstanding")

_DEFAULT_VECTOR_STORE_NAME: str = "cu_extracted_docs"


class FileSearchBackend(ABC):
    """Abstract interface for vector store operations and file_search tool creation.

    Implementations handle the differences between OpenAI and Foundry APIs:
    - Vector store lifecycle (create, delete)
    - File upload (different ``purpose`` values)
    - Tool format (dict vs SDK typed object)
    """

    @abstractmethod
    async def create_vector_store(self, name: str = _DEFAULT_VECTOR_STORE_NAME) -> str:
        """Create a new vector store and return its ID."""

    @abstractmethod
    async def delete_vector_store(self, vector_store_id: str) -> None:
        """Delete a vector store by ID."""

    @abstractmethod
    async def upload_file(self, vector_store_id: str, filename: str, content: bytes) -> str:
        """Upload a file to a vector store and return the file ID."""

    @abstractmethod
    async def delete_file(self, file_id: str) -> None:
        """Delete a previously uploaded file by ID."""

    @abstractmethod
    def make_tool(self, vector_store_ids: list[str]) -> Any:
        """Create a file_search tool in the format expected by the LLM client."""


class _OpenAICompatBackend(FileSearchBackend):
    """Shared base for OpenAI-compatible vector store backends.

    Both OpenAI and Foundry use the same ``client.vector_stores.*`` and
    ``client.files.*`` API surface. Subclasses only override the file
    upload ``purpose`` and ``make_tool`` format.
    """

    _FILE_PURPOSE: str  # Subclasses must set this

    def __init__(self, client: Any) -> None:
        self._client = client

    async def create_vector_store(self, name: str = _DEFAULT_VECTOR_STORE_NAME) -> str:
        """Create an ephemeral vector store with a 1-day expiration safety net."""
        vs = await self._client.vector_stores.create(
            name=name,
            expires_after={"anchor": "last_active_at", "days": 1},
        )
        return vs.id  # type: ignore[no-any-return]

    async def delete_vector_store(self, vector_store_id: str) -> None:
        await self._client.vector_stores.delete(vector_store_id)

    async def upload_file(self, vector_store_id: str, filename: str, content: bytes) -> str:
        uploaded = await self._client.files.create(
            file=(filename, io.BytesIO(content)),
            purpose=self._FILE_PURPOSE,
        )
        await self._client.vector_stores.files.create(
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

    def make_tool(self, vector_store_ids: list[str]) -> Any:
        return {"type": "file_search", "vector_store_ids": vector_store_ids}


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

    def make_tool(self, vector_store_ids: list[str]) -> Any:
        from azure.ai.projects.models import FileSearchTool

        return FileSearchTool(vector_store_ids=vector_store_ids)
