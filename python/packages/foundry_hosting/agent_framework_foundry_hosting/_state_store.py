# Copyright (c) Microsoft. All rights reserved.


from abc import ABC, abstractmethod
from datetime import datetime
from typing import Generic, Protocol, TypeVar

from agent_framework import (
    AgentSession,
    CheckpointID,
    CheckpointStorage,
    Content,
    SessionStore,
    WorkflowCheckpoint,
    WorkflowCheckpointException,
)
from azure.ai.agentserver.core import AgentConfig, FoundryAgentRequestContext
from azure.ai.agentserver.core.storage import FoundryStateStore, FoundryStorageConflictError

StoreT = TypeVar("StoreT")


class StoreProvider(ABC, Generic[StoreT]):
    """Provide store for a hosting environment."""

    @abstractmethod
    def get_store(self, *, config: AgentConfig, platform_context: FoundryAgentRequestContext) -> StoreT:
        """Get store for a hosting environment.

        Args:
            config: The resolved agent server configuration.
            platform_context: The request-scoped platform context for the current request.

        Returns:
            The store instance for the given hosting environment.
        """


class ContextScopedStoreProvider(ABC, Generic[StoreT]):
    """Provide a context-scoped store for a hosting environment.

    Use this when state must be queried or managed as a collection belonging to
    one context, rather than accessed only by an individual item ID. The context
    can be a conversation ID or another identifier that groups related state.
    """

    @abstractmethod
    def get_store(
        self,
        *,
        config: AgentConfig,
        context_id: str,
        platform_context: FoundryAgentRequestContext,
    ) -> StoreT:
        """Get a context-scoped store for a hosting environment.

        Args:
            config: The resolved agent server configuration.
            context_id: A string that uniquely identifies the context for which the store is scoped.
            platform_context: The request-scoped platform context for the current request.

        Returns:
            The store instance for the given hosting environment and context ID.
        """


# region Checkpoint persistence


class FoundryCheckpointStore:
    """Checkpoint store backed by the `FoundryStateStore`."""

    DEFAULT_ROOT_SCOPE = "checkpoints"

    def __init__(self, context_id: str, platform_context: FoundryAgentRequestContext) -> None:
        """Initialize a Foundry-scoped checkpoint store for the given context ID.

        Args:
            context_id: A string that uniquely identifies the context for which the checkpoint store is scoped.
                        This can be used to isolate checkpoints for different workflow runs.
            platform_context: The request-scoped platform context for the current request.
        """
        if not context_id:
            raise ValueError("context_id must be provided to initialize a FoundryCheckpointStore.")

        self.context_id = context_id
        self.platform_context = platform_context

    async def _get_store(self) -> FoundryStateStore:
        return await FoundryStateStore.get_or_create(
            f"{self.DEFAULT_ROOT_SCOPE}/{self.context_id}",
            user_isolation=True,
        )

    async def save(self, checkpoint: WorkflowCheckpoint) -> CheckpointID:
        """Save a workflow checkpoint to the store.

        Args:
            checkpoint: The workflow checkpoint to save.

        The checkpoint will be serialized to a dictionary and then encoded before being stored.

        Returns:
            The ID of the saved checkpoint.
        """
        from agent_framework._workflows._checkpoint_encoding import encode_checkpoint_value

        encoded_checkpoint = encode_checkpoint_value(checkpoint.to_dict())

        store = await self._get_store()
        async with store:
            await store.set_item(checkpoint.checkpoint_id, encoded_checkpoint, call_id=self.platform_context.call_id)
            return checkpoint.checkpoint_id

    async def load(self, checkpoint_id: CheckpointID) -> WorkflowCheckpoint:
        """Load a workflow checkpoint from the store.

        Args:
            checkpoint_id: The ID of the checkpoint to load.

        Returns:
            The loaded workflow checkpoint.

        Raises:
            WorkflowCheckpointException: If no checkpoint is found with the given ID.
        """
        from agent_framework._workflows._checkpoint_encoding import decode_checkpoint_value

        store = await self._get_store()
        async with store:
            item = await store.get_item(checkpoint_id, call_id=self.platform_context.call_id)
        if item is None:
            raise WorkflowCheckpointException(f"No checkpoint found with ID {checkpoint_id}")
        return WorkflowCheckpoint.from_dict(decode_checkpoint_value(item.value))

    async def list_checkpoints(self, *, workflow_name: str) -> list[WorkflowCheckpoint]:
        """List all workflow checkpoints for a given workflow name."""
        from agent_framework._workflows._checkpoint_encoding import decode_checkpoint_value

        store = await self._get_store()
        checkpoints: list[WorkflowCheckpoint] = []
        after: str | None = None
        async with store:
            while True:
                page = await store.list_keys(after=after, call_id=self.platform_context.call_id)
                for item_key in page.keys:
                    item = await store.get_item(item_key.key, call_id=self.platform_context.call_id)
                    if item is None:
                        continue
                    checkpoint = WorkflowCheckpoint.from_dict(decode_checkpoint_value(item.value))
                    if checkpoint.workflow_name == workflow_name:
                        checkpoints.append(checkpoint)
                if not page.has_more or page.last_id is None:
                    break
                after = page.last_id
        return checkpoints

    async def delete(self, checkpoint_id: CheckpointID) -> bool:
        store = await self._get_store()
        async with store:
            deleted_item = await store.delete_item(checkpoint_id, call_id=self.platform_context.call_id)
        return deleted_item.id is not None

    async def get_latest(self, *, workflow_name: str) -> WorkflowCheckpoint | None:
        checkpoints = await self.list_checkpoints(workflow_name=workflow_name)
        if not checkpoints:
            return None
        return max(checkpoints, key=lambda checkpoint: datetime.fromisoformat(checkpoint.timestamp))

    async def list_checkpoint_ids(self, *, workflow_name: str) -> list[CheckpointID]:
        checkpoints = await self.list_checkpoints(workflow_name=workflow_name)
        return [checkpoint.checkpoint_id for checkpoint in checkpoints]


class CheckpointStoreProvider(ContextScopedStoreProvider[CheckpointStorage]):
    """Provide workflow checkpoint store scoped to a context.

    A workflow context can contain multiple checkpoints. Scoping establishes the
    collection boundary used to list checkpoints, restore the latest checkpoint,
    and clean up older checkpoints without affecting another workflow context.

    This defaults to using the `FoundryCheckpointStore` in all environments.
    """

    def get_store(
        self,
        *,
        config: AgentConfig,
        context_id: str,
        platform_context: FoundryAgentRequestContext,
    ) -> CheckpointStorage:
        """Get checkpoint store for the requested hosting environment."""
        if not context_id:
            raise ValueError("context_id must be provided to get a checkpoint store.")

        return FoundryCheckpointStore(context_id, platform_context)


# endregion Checkpoint persistence

# region Function approval persistence


class FunctionApprovalStore(Protocol):
    """Store for saving function approval requests."""

    async def save_approval_request(self, approval_request_id: str, request: Content) -> None:
        """Save a function approval request under the given ID."""
        ...

    async def load_approval_request(self, approval_request_id: str) -> Content:
        """Load a function approval request by its ID."""
        ...


class FoundryFunctionApprovalStore:
    """Function approval store backed by the `FoundryStateStore`.

    This storage implements a hybrid approach where the checkpoint metadata and structure are
    stored in JSON format, while the actual state data (which may contain complex Python objects)
    is serialized using pickle and embedded as base64-encoded strings within the JSON. This allows
    for human-readable checkpoint files while preserving the ability to store complex Python objects.
    """

    DEFAULT_ROOT_SCOPE = "function_approvals"

    def __init__(self, platform_context: FoundryAgentRequestContext) -> None:
        self.platform_context = platform_context

    async def _get_store(self) -> FoundryStateStore:
        return await FoundryStateStore.get_or_create(
            self.DEFAULT_ROOT_SCOPE,
            user_isolation=True,
        )

    async def save_approval_request(self, approval_request_id: str, request: Content) -> None:
        store = await self._get_store()
        async with store:
            try:
                await store.create_item(approval_request_id, request.to_dict(), call_id=self.platform_context.call_id)
            except FoundryStorageConflictError as ex:
                raise ValueError(f"Approval request with ID '{approval_request_id}' already exists.") from ex

    async def load_approval_request(self, approval_request_id: str) -> Content:
        store = await self._get_store()
        async with store:
            item = await store.get_item(approval_request_id, call_id=self.platform_context.call_id)
        if item is None:
            raise KeyError(f"Approval request with ID '{approval_request_id}' does not exist.")
        return Content.from_dict(item.value)


class FunctionApprovalStoreProvider(StoreProvider[FunctionApprovalStore]):
    """Provide function approval store for the active hosting environment.

    This defaults to using the `FoundryFunctionApprovalStore` in all environments.
    """

    def get_store(self, *, config: AgentConfig, platform_context: FoundryAgentRequestContext) -> FunctionApprovalStore:
        """Get function approval store for the requested hosting environment."""
        return FoundryFunctionApprovalStore(platform_context)


# endregion Function approval persistence

# region Agent session persistence


class FoundryAgentSessionStore(SessionStore):
    """Agent session store backed by the `FoundryStateStore`."""

    DEFAULT_ROOT_SCOPE = "agent_sessions"

    def __init__(self, platform_context: FoundryAgentRequestContext) -> None:
        self.platform_context = platform_context

    async def _get_store(self) -> FoundryStateStore:
        return await FoundryStateStore.get_or_create(
            f"{self.DEFAULT_ROOT_SCOPE}",
            user_isolation=True,
        )

    async def get(self, session_id: str) -> AgentSession | None:
        store = await self._get_store()
        async with store:
            item = await store.get_item(session_id, call_id=self.platform_context.call_id)
        if item is None:
            return None
        return AgentSession.from_dict(item.value)

    async def set(self, session_id: str, session: AgentSession) -> None:
        store = await self._get_store()
        async with store:
            await store.set_item(session_id, session.to_dict(), call_id=self.platform_context.call_id)

    async def delete(self, session_id: str) -> None:
        store = await self._get_store()
        async with store:
            await store.delete_item(session_id, call_id=self.platform_context.call_id)


class AgentSessionStoreProvider(StoreProvider[SessionStore]):
    """Provide agent session store for the active hosting environment.

    This defaults to using the `FoundryAgentSessionStore` in all environments.
    """

    def get_store(self, *, config: AgentConfig, platform_context: FoundryAgentRequestContext) -> SessionStore:
        """Get agent session store for the requested hosting environment."""
        return FoundryAgentSessionStore(platform_context)


# endregion Agent session persistence
