# Copyright (c) Microsoft. All rights reserved.

"""Azure Cosmos DB checkpoint storage for workflow checkpointing."""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from agent_framework import AGENT_FRAMEWORK_USER_AGENT
from agent_framework._settings import SecretString, load_settings
from agent_framework._workflows._checkpoint import CheckpointID, WorkflowCheckpoint
from agent_framework._workflows._checkpoint_encoding import decode_checkpoint_value, encode_checkpoint_value
from agent_framework.exceptions import WorkflowCheckpointException
from azure.core.credentials import TokenCredential
from azure.core.credentials_async import AsyncTokenCredential
from azure.cosmos import PartitionKey
from azure.cosmos.aio import ContainerProxy, CosmosClient
from azure.cosmos.exceptions import CosmosResourceNotFoundError

AzureCredentialTypes = TokenCredential | AsyncTokenCredential

logger = logging.getLogger(__name__)


class AzureCosmosCheckpointSettings(TypedDict, total=False):
    """Settings for CosmosCheckpointStorage resolved from args and environment."""

    endpoint: str | None
    database_name: str | None
    container_name: str | None
    key: SecretString | None


class CosmosCheckpointStorage:
    """Azure Cosmos DB-backed checkpoint storage for workflow checkpointing.

    Implements the ``CheckpointStorage`` protocol using Azure Cosmos DB NoSQL
    as the persistent backend. Checkpoints are stored as JSON documents with
    ``workflow_name`` as the partition key, enabling efficient per-workflow queries.

    This storage uses the same hybrid JSON + pickle encoding as
    ``FileCheckpointStorage``, allowing full Python object fidelity for
    complex workflow state while keeping the document structure human-readable.

    SECURITY WARNING: Checkpoints use pickle for data serialization. Only load
    checkpoints from trusted sources. Loading a malicious checkpoint can execute
    arbitrary code.

    The database and container are created automatically on first use
    if they do not already exist. The container uses partition key
    ``/workflow_name``.

    Example using managed identity / RBAC:

    .. code-block:: python

        from azure.identity.aio import DefaultAzureCredential
        from agent_framework_azure_cosmos import CosmosCheckpointStorage

        storage = CosmosCheckpointStorage(
            endpoint="https://my-account.documents.azure.com:443/",
            credential=DefaultAzureCredential(),
            database_name="agent-db",
            container_name="checkpoints",
        )

    Example using account key:

    .. code-block:: python

        storage = CosmosCheckpointStorage(
            endpoint="https://my-account.documents.azure.com:443/",
            credential="my-account-key",
            database_name="agent-db",
            container_name="checkpoints",
        )

    Then use with a workflow builder:

    .. code-block:: python

        workflow = WorkflowBuilder(
            start_executor=start,
            checkpoint_storage=storage,
        ).build()
    """

    def __init__(
        self,
        *,
        endpoint: str | None = None,
        database_name: str | None = None,
        container_name: str | None = None,
        credential: str | AzureCredentialTypes | None = None,
        cosmos_client: CosmosClient | None = None,
        container_client: ContainerProxy | None = None,
        env_file_path: str | None = None,
        env_file_encoding: str | None = None,
    ) -> None:
        """Initialize the Azure Cosmos DB checkpoint storage.

        Supports multiple authentication modes:

        - **Container client** (``container_client``): Use a pre-created
          Cosmos async container proxy. No client lifecycle is managed.
        - **Cosmos client** (``cosmos_client``): Use a pre-created Cosmos
          async client. The caller is responsible for closing it.
        - **Endpoint + credential**: Create a new Cosmos client. The storage
          owns the client and closes it on ``close()``.
        - **Environment variables**: Falls back to ``AZURE_COSMOS_ENDPOINT``,
          ``AZURE_COSMOS_DATABASE_NAME``, ``AZURE_COSMOS_CONTAINER_NAME``,
          and ``AZURE_COSMOS_KEY``.

        Args:
            endpoint: Cosmos DB account endpoint.
                Can be set via ``AZURE_COSMOS_ENDPOINT``.
            database_name: Cosmos DB database name.
                Can be set via ``AZURE_COSMOS_DATABASE_NAME``.
            container_name: Cosmos DB container name.
                Can be set via ``AZURE_COSMOS_CONTAINER_NAME``.
            credential: Credential to authenticate with Cosmos DB.
                For **managed identity / RBAC**, pass an Azure credential object
                such as ``DefaultAzureCredential()`` or
                ``ManagedIdentityCredential()``.
                For **key-based auth**, pass the account key as a string,
                or set ``AZURE_COSMOS_KEY`` in the environment.
            cosmos_client: Pre-created Cosmos async client.
            container_client: Pre-created Cosmos container client.
            env_file_path: Path to environment file for loading settings.
            env_file_encoding: Encoding of the environment file.
        """
        self._cosmos_client: CosmosClient | None = cosmos_client
        self._container_proxy: ContainerProxy | None = container_client
        self._owns_client = False

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
            AzureCosmosCheckpointSettings,
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

    async def save(self, checkpoint: WorkflowCheckpoint) -> CheckpointID:
        """Save a checkpoint to Cosmos DB and return its ID.

        The checkpoint is encoded to a JSON-compatible form (using pickle for
        non-JSON-native values) and stored as a Cosmos DB document with the
        ``workflow_name`` as the partition key.

        The document ``id`` is a composite of ``workflow_name`` and
        ``checkpoint_id`` to ensure global uniqueness across partitions.

        Args:
            checkpoint: The WorkflowCheckpoint object to save.

        Returns:
            The unique ID of the saved checkpoint.
        """
        await self._ensure_container_proxy()

        checkpoint_dict = checkpoint.to_dict()
        encoded = encode_checkpoint_value(checkpoint_dict)

        document: dict[str, Any] = {
            "id": self._make_document_id(checkpoint.workflow_name, checkpoint.checkpoint_id),
            "workflow_name": checkpoint.workflow_name,
            **encoded,
        }

        await self._container_proxy.upsert_item(body=document)  # type: ignore[union-attr]
        logger.info("Saved checkpoint %s to Cosmos DB", checkpoint.checkpoint_id)
        return checkpoint.checkpoint_id

    async def load(self, checkpoint_id: CheckpointID) -> WorkflowCheckpoint:
        """Load a checkpoint from Cosmos DB by ID.

        Args:
            checkpoint_id: The unique ID of the checkpoint to load.

        Returns:
            The WorkflowCheckpoint object corresponding to the given ID.

        Raises:
            WorkflowCheckpointException: If no checkpoint with the given ID exists,
                or if multiple checkpoints share the same ID across workflows.
        """
        await self._ensure_container_proxy()

        query = "SELECT * FROM c WHERE c.checkpoint_id = @checkpoint_id"
        parameters: list[dict[str, object]] = [
            {"name": "@checkpoint_id", "value": checkpoint_id},
        ]

        items = self._container_proxy.query_items(  # type: ignore[union-attr]
            query=query,
            parameters=parameters,
        )

        results: list[dict[str, Any]] = []
        async for item in items:
            results.append(item)

        if not results:
            raise WorkflowCheckpointException(f"No checkpoint found with ID {checkpoint_id}")

        if len(results) > 1:
            workflow_names = [r.get("workflow_name", "unknown") for r in results]
            raise WorkflowCheckpointException(
                f"Multiple checkpoints found with ID {checkpoint_id} across workflows: "
                f"{workflow_names}. Use list_checkpoints(workflow_name=...) to query "
                f"by workflow instead."
            )

        return self._document_to_checkpoint(results[0])

    async def list_checkpoints(self, *, workflow_name: str) -> list[WorkflowCheckpoint]:
        """List checkpoint objects for a given workflow name.

        Args:
            workflow_name: The name of the workflow to list checkpoints for.

        Returns:
            A list of WorkflowCheckpoint objects for the specified workflow name.
        """
        await self._ensure_container_proxy()

        query = "SELECT * FROM c WHERE c.workflow_name = @workflow_name ORDER BY c.timestamp ASC"
        parameters: list[dict[str, object]] = [
            {"name": "@workflow_name", "value": workflow_name},
        ]

        items = self._container_proxy.query_items(  # type: ignore[union-attr]
            query=query,
            parameters=parameters,
            partition_key=workflow_name,
        )

        checkpoints: list[WorkflowCheckpoint] = []
        async for item in items:
            try:
                checkpoints.append(self._document_to_checkpoint(item))
            except Exception as e:
                logger.warning("Failed to decode checkpoint document: %s", e)
        return checkpoints

    async def delete(self, checkpoint_id: CheckpointID) -> bool:
        """Delete a checkpoint from Cosmos DB by ID.

        Args:
            checkpoint_id: The unique ID of the checkpoint to delete.

        Returns:
            True if the checkpoint was successfully deleted, False if not found.
        """
        await self._ensure_container_proxy()

        query = "SELECT c.id, c.workflow_name FROM c WHERE c.checkpoint_id = @checkpoint_id"
        parameters: list[dict[str, object]] = [
            {"name": "@checkpoint_id", "value": checkpoint_id},
        ]

        items = self._container_proxy.query_items(  # type: ignore[union-attr]
            query=query,
            parameters=parameters,
        )

        async for item in items:
            try:
                await self._container_proxy.delete_item(  # type: ignore[union-attr]
                    item=item["id"],
                    partition_key=item["workflow_name"],
                )
                logger.info("Deleted checkpoint %s from Cosmos DB", checkpoint_id)
                return True
            except CosmosResourceNotFoundError:
                return False

        return False

    async def get_latest(self, *, workflow_name: str) -> WorkflowCheckpoint | None:
        """Get the latest checkpoint for a given workflow name.

        Args:
            workflow_name: The name of the workflow to get the latest checkpoint for.

        Returns:
            The latest WorkflowCheckpoint, or None if no checkpoints exist.
        """
        await self._ensure_container_proxy()

        query = "SELECT * FROM c WHERE c.workflow_name = @workflow_name ORDER BY c.timestamp DESC OFFSET 0 LIMIT 1"
        parameters: list[dict[str, object]] = [
            {"name": "@workflow_name", "value": workflow_name},
        ]

        items = self._container_proxy.query_items(  # type: ignore[union-attr]
            query=query,
            parameters=parameters,
            partition_key=workflow_name,
        )

        async for item in items:
            checkpoint = self._document_to_checkpoint(item)
            logger.debug(
                "Latest checkpoint for workflow %s is %s",
                workflow_name,
                checkpoint.checkpoint_id,
            )
            return checkpoint

        return None

    async def list_checkpoint_ids(self, *, workflow_name: str) -> list[CheckpointID]:
        """List checkpoint IDs for a given workflow name.

        Args:
            workflow_name: The name of the workflow to list checkpoint IDs for.

        Returns:
            A list of checkpoint IDs for the specified workflow name.
        """
        await self._ensure_container_proxy()

        query = "SELECT c.checkpoint_id FROM c WHERE c.workflow_name = @workflow_name ORDER BY c.timestamp ASC"
        parameters: list[dict[str, object]] = [
            {"name": "@workflow_name", "value": workflow_name},
        ]

        items = self._container_proxy.query_items(  # type: ignore[union-attr]
            query=query,
            parameters=parameters,
            partition_key=workflow_name,
        )

        checkpoint_ids: list[CheckpointID] = []
        async for item in items:
            cid = item.get("checkpoint_id")
            if isinstance(cid, str):
                checkpoint_ids.append(cid)
        return checkpoint_ids

    async def close(self) -> None:
        """Close the underlying Cosmos client when this storage owns it."""
        if self._owns_client and self._cosmos_client is not None:
            await self._cosmos_client.close()

    async def __aenter__(self) -> CosmosCheckpointStorage:
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
        """Get or create the Cosmos DB database and container for storing checkpoints."""
        if self._container_proxy is not None:
            return
        if self._cosmos_client is None:
            raise RuntimeError("Cosmos client is not initialized.")

        database = await self._cosmos_client.create_database_if_not_exists(id=self.database_name)
        self._container_proxy = await database.create_container_if_not_exists(
            id=self.container_name,
            partition_key=PartitionKey(path="/workflow_name"),
        )

    @staticmethod
    def _document_to_checkpoint(document: dict[str, Any]) -> WorkflowCheckpoint:
        """Convert a Cosmos DB document back to a WorkflowCheckpoint.

        Strips Cosmos DB system properties (``_rid``, ``_self``, ``_etag``,
        ``_attachments``, ``_ts``) before decoding.
        """
        # Remove Cosmos DB system properties and the composite 'id' field
        # (checkpoints use 'checkpoint_id', not 'id')
        cosmos_keys = {"id", "_rid", "_self", "_etag", "_attachments", "_ts"}
        cleaned = {k: v for k, v in document.items() if k not in cosmos_keys}

        decoded = decode_checkpoint_value(cleaned)
        return WorkflowCheckpoint.from_dict(decoded)

    @staticmethod
    def _make_document_id(workflow_name: str, checkpoint_id: str) -> str:
        """Create a composite Cosmos DB document ID.

        Combines ``workflow_name`` and ``checkpoint_id`` to ensure global
        uniqueness across partitions.
        """
        return f"{workflow_name}_{checkpoint_id}"
