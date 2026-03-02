# Copyright (c) Microsoft. All rights reserved.

"""Azure Cosmos DB history provider."""

from __future__ import annotations

import time
import uuid
from collections.abc import Sequence
from typing import Any, ClassVar, TypedDict

from agent_framework import AGENT_FRAMEWORK_USER_AGENT, Message
from agent_framework._sessions import BaseHistoryProvider
from agent_framework._settings import SecretString, load_settings
from agent_framework.azure._entra_id_authentication import AzureCredentialTypes
from azure.cosmos import PartitionKey
from azure.cosmos.aio import ContainerProxy, CosmosClient, DatabaseProxy


class AzureCosmosHistorySettings(TypedDict, total=False):
    """Settings for CosmosHistoryProvider resolved from args and environment."""

    endpoint: str | None
    database_name: str | None
    container_name: str | None
    key: SecretString | None


class CosmosHistoryProvider(BaseHistoryProvider):
    """Azure Cosmos DB-backed history provider using BaseHistoryProvider hooks."""

    DEFAULT_SOURCE_ID: ClassVar[str] = "azure_cosmos_history"
    _BATCH_OPERATION_LIMIT: ClassVar[int] = 100

    def __init__(
        self,
        source_id: str = DEFAULT_SOURCE_ID,
        *,
        load_messages: bool = True,
        store_outputs: bool = True,
        store_inputs: bool = True,
        store_context_messages: bool = False,
        store_context_from: set[str] | None = None,
        endpoint: str | None = None,
        database_name: str | None = None,
        container_name: str | None = None,
        credential: str | AzureCredentialTypes | None = None,
        cosmos_client: CosmosClient | None = None,
        container_client: ContainerProxy | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize the Azure Cosmos DB history provider.

        Args:
            source_id: Unique identifier for this provider instance.
            load_messages: Whether to load messages before invocation.
            store_outputs: Whether to store response messages.
            store_inputs: Whether to store input messages.
            store_context_messages: Whether to store context from other providers.
            store_context_from: If set, only store context from these source_ids.
            endpoint: Cosmos DB account endpoint.
                Can be set via ``AZURE_COSMOS_ENDPOINT``.
            database_name: Cosmos DB database name.
                Can be set via ``AZURE_COSMOS_DATABASE_NAME``.
            container_name: Cosmos DB container name.
                Can be set via ``AZURE_COSMOS_CONTAINER_NAME``.
            credential: Credential to authenticate with Cosmos DB.
                Supports key string and Azure credential objects.
                Can be set via ``AZURE_COSMOS_KEY`` when omitted.
            cosmos_client: Pre-created Cosmos async client.
            container_client: Pre-created Cosmos container client for fixed-container usage.
            env_file_path: Path to environment file for loading settings.
            env_file_encoding: Encoding of the environment file.
        """
        super().__init__(
            source_id,
            load_messages=load_messages,
            store_outputs=store_outputs,
            store_inputs=store_inputs,
            store_context_messages=store_context_messages,
            store_context_from=store_context_from,
        )

        self._cosmos_client: CosmosClient | None = cosmos_client
        self._container_proxy: ContainerProxy | None = container_client
        self._owns_client = False
        self._database_client: DatabaseProxy | None = None

        if self._container_proxy is not None:
            self.database_name: str = database_name or ""
            self.container_name: str = container_name or ""
            return

        required_fields: list[str] = ["database_name", "container_name"]
        if cosmos_client is None:
            required_fields.append("endpoint")
            if credential is None:
                required_fields.append("key")

        settings = load_settings(
            AzureCosmosHistorySettings,
            env_prefix="AZURE_COSMOS_",
            required_fields=required_fields,
            endpoint=endpoint,
            database_name=database_name,
            container_name=container_name,
            key=credential if isinstance(credential, str) else None,
            env_file_path=env_file_path,
            env_file_encoding=env_file_encoding,
        )
        self.database_name = settings["database_name"]  # type: ignore[assignment]
        self.container_name = settings["container_name"]  # type: ignore[assignment]
        if self._cosmos_client is None:
            self._cosmos_client = CosmosClient(
                url=settings["endpoint"],  # type: ignore[arg-type]
                credential=credential or settings["key"].get_secret_value(),  # type: ignore[arg-type,union-attr]
                user_agent_suffix=AGENT_FRAMEWORK_USER_AGENT,
            )
            self._owns_client = True

        self._database_client = self._cosmos_client.get_database_client(self.database_name)


    async def get_messages(self, session_id: str | None, **kwargs: Any) -> list[Message]:
        """Retrieve stored messages for this session from Azure Cosmos DB."""
        await self._ensure_container_proxy()
        session_key = self._session_partition_key(session_id)

        query = (
            "SELECT c.message FROM c "
            "WHERE c.session_id = @session_id AND c.source_id = @source_id "
            "ORDER BY c.sort_key ASC"
        )
        parameters: list[dict[str, object]] = [
            {"name": "@session_id", "value": session_key},
            {"name": "@source_id", "value": self.source_id},
        ]
        items = self._container_proxy.query_items(  # type: ignore[union-attr]
            query=query, parameters=parameters, partition_key=session_key
        )

        messages: list[Message] = []
        async for item in items:
            message_payload = item.get("message")
            if isinstance(message_payload, dict):
                messages.append(Message.from_dict(message_payload))

        return messages

    async def save_messages(self, session_id: str | None, messages: Sequence[Message], **kwargs: Any) -> None:
        """Persist messages for this session to Azure Cosmos DB."""
        if not messages:
            return

        await self._ensure_container_proxy()
        session_key = self._session_partition_key(session_id)

        base_sort_key = time.time_ns()
        operations: list[tuple[str, tuple[dict[str, Any]]]] = []
        for index, message in enumerate(messages):
            document = {
                "id": str(uuid.uuid4()),
                "session_id": session_key,
                "sort_key": base_sort_key + index,
                "source_id": self.source_id,
                "message": message.to_dict(),
            }
            operations.append(("upsert", (document,)))

        for start in range(0, len(operations), self._BATCH_OPERATION_LIMIT):
            batch = operations[start : start + self._BATCH_OPERATION_LIMIT]
            await self._container_proxy.execute_item_batch(  # type: ignore[union-attr]
                batch_operations=batch, partition_key=session_key
            )

    async def clear(self, session_id: str | None) -> None:
        """Clear all messages for a session from Azure Cosmos DB."""
        await self._ensure_container_proxy()
        session_key = self._session_partition_key(session_id)
        query = "SELECT c.id FROM c WHERE c.session_id = @session_id AND c.source_id = @source_id"
        parameters: list[dict[str, object]] = [
            {"name": "@session_id", "value": session_key},
            {"name": "@source_id", "value": self.source_id},
        ]
        items = self._container_proxy.query_items(  # type: ignore[union-attr]
            query=query, parameters=parameters, partition_key=session_key
        )

        delete_operations: list[tuple[str, tuple[str]]] = []
        async for item in items:
            item_id = item.get("id")
            if isinstance(item_id, str):
                delete_operations.append(("delete", (item_id,)))

        for start in range(0, len(delete_operations), self._BATCH_OPERATION_LIMIT):
            batch = delete_operations[start : start + self._BATCH_OPERATION_LIMIT]
            await self._container_proxy.execute_item_batch(  # type: ignore[union-attr]
                batch_operations=batch, partition_key=session_key
            )

    async def list_sessions(self) -> list[str]:
        """List all session IDs stored in this provider's Cosmos container."""
        await self._ensure_container_proxy()
        query = (
            "SELECT DISTINCT VALUE c.session_id FROM c WHERE c.source_id = @source_id"
        )
        parameters: list[dict[str, object]] = [
            {"name": "@source_id", "value": self.source_id}
        ]
        items = self._container_proxy.query_items(  # type: ignore[union-attr]
            query=query, parameters=parameters, enable_cross_partition_query=True
        )

        session_ids: set[str] = set()
        async for item in items:
            if isinstance(item, str):
                session_ids.add(item)
        return sorted(session_ids)

    async def close(self) -> None:
        """Close the underlying Cosmos client when this provider owns it."""
        if self._owns_client and self._cosmos_client is not None:
            await self._cosmos_client.close()

    async def __aenter__(self) -> CosmosHistoryProvider:
        """Async context manager entry."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Async context manager exit."""
        try:
            await self.close()
        except Exception:
            if exc_type is None:
                raise

    async def _ensure_container_proxy(self) -> None:
        """Get or create the Cosmos DB container for storing messages."""
        if self._container_proxy is not None:
            return
        if self._database_client is None:
            raise RuntimeError("Cosmos database client is not initialized.")

        self._container_proxy = (
            await self._database_client.create_container_if_not_exists(
                id=self.container_name,
                partition_key=PartitionKey(path="/session_id"),
            )
        )

    @staticmethod
    def _session_partition_key(session_id: str | None) -> str:
        return session_id or "default"
