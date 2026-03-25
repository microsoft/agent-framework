# Copyright (c) Microsoft. All rights reserved.
"""
Cosmos DB Storage for Thread Metadata

This module provides persistent storage for conversation thread metadata
using Azure Cosmos DB. Message storage is handled separately by the
CosmosHistoryProvider from agent-framework-azure-cosmos package.

Document Types:
- Thread: {"type": "thread", "id": "thread_xxx", "thread_id": "thread_xxx", ...}

Note: Conversation messages are managed by CosmosHistoryProvider which uses
session_id (thread_id) as the partition key for efficient message retrieval.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any

from azure.cosmos import CosmosClient
from azure.cosmos.exceptions import CosmosResourceNotFoundError
from azure.identity import DefaultAzureCredential


class CosmosConversationStore:
    """
    Manages conversation thread metadata in Azure Cosmos DB.

    Thread metadata includes: user_id, title, status, created_at, updated_at.
    Message persistence is handled by CosmosHistoryProvider (context provider).
    """

    def __init__(
        self,
        endpoint: str | None = None,
        database_name: str | None = None,
        container_name: str | None = None,
        credential: Any | None = None,
    ):
        """
        Initialize the Cosmos DB conversation store.

        Args:
            endpoint: Cosmos DB endpoint URL. Defaults to AZURE_COSMOS_ENDPOINT env var.
            database_name: Database name. Defaults to AZURE_COSMOS_DATABASE_NAME env var.
            container_name: Container name for threads. Defaults to AZURE_COSMOS_THREADS_CONTAINER_NAME.
            credential: Azure credential. Defaults to DefaultAzureCredential.
        """
        self.endpoint = endpoint or os.environ.get("AZURE_COSMOS_ENDPOINT")
        self.database_name = database_name or os.environ.get(
            "AZURE_COSMOS_DATABASE_NAME", "chat_db"
        )
        self.container_name = container_name or os.environ.get(
            "AZURE_COSMOS_THREADS_CONTAINER_NAME", "threads"
        )

        if not self.endpoint:
            raise ValueError(
                "Cosmos DB endpoint is required. "
                "Set AZURE_COSMOS_ENDPOINT environment variable."
            )

        self.credential = credential or DefaultAzureCredential()
        self._client: CosmosClient | None = None
        self._container = None

    @property
    def container(self):
        """Lazy initialization of Cosmos DB container client with auto-create."""
        if self._container is None:
            self._client = CosmosClient(self.endpoint, credential=self.credential)
            # Create database if it doesn't exist
            database = self._client.create_database_if_not_exists(id=self.database_name)
            # Create container with thread_id as partition key
            self._container = database.create_container_if_not_exists(
                id=self.container_name,
                partition_key={"paths": ["/thread_id"], "kind": "Hash"},
            )
            logging.info(
                f"Initialized Cosmos container: {self.database_name}/{self.container_name}"
            )
        return self._container

    # -------------------------------------------------------------------------
    # Thread Operations
    # -------------------------------------------------------------------------

    async def create_thread(
        self,
        thread_id: str,
        user_id: str,
        title: str | None = None,
        metadata: dict | None = None,
    ) -> dict:
        """
        Create a new conversation thread.

        Args:
            thread_id: Unique thread identifier.
            user_id: Owner's user ID.
            title: Optional thread title.
            metadata: Optional custom metadata.

        Returns:
            The created thread document.
        """
        now = datetime.now(timezone.utc).isoformat()
        thread = {
            "id": thread_id,
            "thread_id": thread_id,  # Partition key
            "type": "thread",
            "user_id": user_id,
            "title": title,
            "status": "active",
            "message_count": 0,
            "created_at": now,
            "updated_at": now,
            "last_message_preview": None,
            "metadata": metadata or {},
        }

        self.container.create_item(body=thread)
        logging.info(f"Created thread {thread_id} for user {user_id} in Cosmos DB")
        return thread

    async def get_thread(self, thread_id: str) -> dict | None:
        """
        Get a thread by ID.

        Args:
            thread_id: Thread identifier.

        Returns:
            Thread document or None if not found.
        """
        try:
            thread = self.container.read_item(
                item=thread_id,
                partition_key=thread_id,
            )
            return thread
        except CosmosResourceNotFoundError:
            return None

    async def delete_thread(self, thread_id: str) -> bool:
        """
        Delete a thread metadata document.

        Note: Messages are stored separately by CosmosHistoryProvider and
        can be cleared using history_provider.clear(session_id=thread_id).

        Args:
            thread_id: Thread identifier.

        Returns:
            True if deleted, False if not found.
        """
        try:
            self.container.delete_item(item=thread_id, partition_key=thread_id)
            logging.info(f"Deleted thread {thread_id} from Cosmos DB")
            return True
        except CosmosResourceNotFoundError:
            return False

    async def update_thread(
        self,
        thread_id: str,
        title: str | None = None,
        status: str | None = None,
        message_count: int | None = None,
        last_message_preview: str | None = None,
    ) -> dict | None:
        """
        Update thread metadata.

        Args:
            thread_id: Thread identifier.
            title: New title (optional).
            status: New status - 'active', 'archived', or 'deleted' (optional).
            message_count: New message count (optional).
            last_message_preview: Preview of last message (optional).

        Returns:
            Updated thread document or None if not found.
        """
        thread = await self.get_thread(thread_id)
        if thread is None:
            return None

        # Update fields
        if title is not None:
            thread["title"] = title
        if status is not None:
            thread["status"] = status
        if message_count is not None:
            thread["message_count"] = message_count
        if last_message_preview is not None:
            thread["last_message_preview"] = last_message_preview

        thread["updated_at"] = datetime.now(timezone.utc).isoformat()

        updated = self.container.replace_item(item=thread_id, body=thread)
        logging.info(f"Updated thread {thread_id}")
        return updated

    async def thread_exists(self, thread_id: str) -> bool:
        """
        Check if a thread exists.

        Args:
            thread_id: Thread identifier.

        Returns:
            True if thread exists, False otherwise.
        """
        thread = await self.get_thread(thread_id)
        return thread is not None

    async def list_threads(
        self,
        user_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """
        List all threads with optional filters.

        Args:
            user_id: Filter by user ID (optional).
            status: Filter by status - 'active', 'archived', 'deleted' (optional).
            limit: Maximum number of threads to return (default 50).
            offset: Number of threads to skip for pagination.

        Returns:
            List of thread documents sorted by updated_at descending.
        """
        # Build query with optional filters
        conditions = ["c.type = 'thread'"]
        parameters = []

        if user_id:
            conditions.append("c.user_id = @user_id")
            parameters.append({"name": "@user_id", "value": user_id})

        if status:
            conditions.append("c.status = @status")
            parameters.append({"name": "@status", "value": status})

        query = f"""
            SELECT * FROM c
            WHERE {' AND '.join(conditions)}
            ORDER BY c.updated_at DESC
            OFFSET @offset LIMIT @limit
        """
        parameters.extend([
            {"name": "@offset", "value": offset},
            {"name": "@limit", "value": limit},
        ])

        items = list(
            self.container.query_items(
                query=query,
                parameters=parameters,
                enable_cross_partition_query=True,
            )
        )

        logging.info(
            f"Listed {len(items)} threads (user_id={user_id}, status={status})"
        )
        return items
