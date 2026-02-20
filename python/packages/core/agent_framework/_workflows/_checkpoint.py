# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, TypeAlias

from ..exceptions import WorkflowCheckpointException

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ._events import WorkflowEvent
    from ._runner_context import WorkflowMessage

# Type alias for checkpoint IDs in case we want to change the
# underlying type in the future (e.g., to UUID or a custom class)
CheckpointID: TypeAlias = str


@dataclass(slots=True)
class WorkflowCheckpoint:
    """Represents a complete checkpoint of workflow state.

    Checkpoints capture the full execution state of a workflow at a specific point,
    enabling workflows to be paused and resumed.

    Note that a checkpoint is not tied to a specific workflow instance, but rather to
    a workflow definition (identified by workflow_name and graph_signature_hash). Thus,
    the ID of the workflow instance that created the checkpoint is not included in the
    checkpoint data. This allows checkpoints to be shared and restored across different
    workflow instances of the same workflow definition.

    Attributes:
        workflow_name: Name of the workflow this checkpoint belongs to. This acts as a
            logical grouping for checkpoints and can be used to filter checkpoints by
            workflow. Workflows with the same name are expected to have compatible graph
            structures for checkpointing.
        graph_signature_hash: Hash of the workflow graph topology to validate checkpoint
            compatibility during restore
        checkpoint_id: Unique identifier for this checkpoint
        previous_checkpoint_id: ID of the previous checkpoint in the chain, if any. This
            allows chaining checkpoints together to form a history of workflow states.
        timestamp: ISO 8601 timestamp when checkpoint was created
        messages: Messages exchanged between executors
        state: Committed workflow state including user data and executor states.
            This contains only committed state; pending state changes are not
            included in checkpoints. Executor states are stored under the
            reserved key '_executor_state'.
        pending_request_info_events: Any pending request info events that have not
            yet been processed at the time of checkpointing. This allows the workflow
            to resume with the correct pending events after a restore.
        iteration_count: Current iteration number when checkpoint was created
        metadata: Additional metadata (e.g., superstep info, graph signature)
        version: Checkpoint format version

    Note:
        The state dict may contain reserved keys managed by the framework.
        See State class documentation for details on reserved keys.
    """

    workflow_name: str
    graph_signature_hash: str

    checkpoint_id: CheckpointID = field(default_factory=lambda: str(uuid.uuid4()))
    previous_checkpoint_id: CheckpointID | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Core workflow state
    messages: dict[str, list[WorkflowMessage]] = field(default_factory=dict)  # type: ignore[misc]
    state: dict[str, Any] = field(default_factory=dict)  # type: ignore[misc]
    pending_request_info_events: dict[str, WorkflowEvent[Any]] = field(default_factory=dict)  # type: ignore[misc]

    # Runtime state
    iteration_count: int = 0

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)  # type: ignore[misc]
    version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        """Convert the WorkflowCheckpoint to a dictionary.

        Notes:
            1. This method does not recursively convert nested dataclasses to dicts.
            2. This is a shallow conversion. The resulting dict will contain the same
               references to nested objects as the original dataclass.
        """
        return {f.name: getattr(self, f.name) for f in fields(self)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> WorkflowCheckpoint:
        """Create a WorkflowCheckpoint from a dictionary.

        Args:
            data: Dictionary containing checkpoint fields.

        Returns:
            A new WorkflowCheckpoint instance.

        Raises:
            WorkflowCheckpointException: If required fields are missing.
        """
        try:
            return cls(**data)
        except Exception as ex:
            raise WorkflowCheckpointException(f"Failed to create WorkflowCheckpoint from dict: {ex}") from ex


class CheckpointStorage(Protocol):
    """Protocol for checkpoint storage backends."""

    async def save(self, checkpoint: WorkflowCheckpoint) -> CheckpointID:
        """Save a checkpoint and return its ID.

        Args:
            checkpoint: The WorkflowCheckpoint object to save.

        Returns:
            The unique ID of the saved checkpoint.
        """
        ...

    async def load(self, checkpoint_id: CheckpointID) -> WorkflowCheckpoint:
        """Load a checkpoint by ID.

        Args:
            checkpoint_id: The unique ID of the checkpoint to load.

        Returns:
            The WorkflowCheckpoint object corresponding to the given ID.

        Raises:
            WorkflowCheckpointException: If no checkpoint with the given ID exists.
        """
        ...

    async def list_checkpoints(self, *, workflow_name: str) -> list[WorkflowCheckpoint]:
        """List checkpoint objects for a given workflow name.

        Args:
            workflow_name: The name of the workflow to list checkpoints for.

        Returns:
            A list of WorkflowCheckpoint objects for the specified workflow name.
        """
        ...

    async def delete(self, checkpoint_id: CheckpointID) -> bool:
        """Delete a checkpoint by ID.

        Args:
            checkpoint_id: The unique ID of the checkpoint to delete.

        Returns:
            True if the checkpoint was successfully deleted, False if no checkpoint with the given ID exists.
        """
        ...

    async def get_latest(self, *, workflow_name: str) -> WorkflowCheckpoint | None:
        """Get the latest checkpoint for a given workflow name.

        Args:
            workflow_name: The name of the workflow to get the latest checkpoint for.

        Returns:
            The latest WorkflowCheckpoint object for the specified workflow name, or None if no checkpoints exist.
        """
        ...

    async def list_checkpoint_ids(self, *, workflow_name: str) -> list[CheckpointID]:
        """List checkpoint IDs for a given workflow name.

        Args:
            workflow_name: The name of the workflow to list checkpoint IDs for.

        Returns:
            A list of checkpoint IDs for the specified workflow name.
        """
        ...


class InMemoryCheckpointStorage:
    """In-memory checkpoint storage for testing and development."""

    def __init__(self) -> None:
        """Initialize the memory storage."""
        self._checkpoints: dict[CheckpointID, WorkflowCheckpoint] = {}

    async def save(self, checkpoint: WorkflowCheckpoint) -> CheckpointID:
        """Save a checkpoint and return its ID."""
        self._checkpoints[checkpoint.checkpoint_id] = copy.deepcopy(checkpoint)
        logger.debug(f"Saved checkpoint {checkpoint.checkpoint_id} to memory")
        return checkpoint.checkpoint_id

    async def load(self, checkpoint_id: CheckpointID) -> WorkflowCheckpoint:
        """Load a checkpoint by ID."""
        checkpoint = self._checkpoints.get(checkpoint_id)
        if checkpoint:
            logger.debug(f"Loaded checkpoint {checkpoint_id} from memory")
            return checkpoint
        raise WorkflowCheckpointException(f"No checkpoint found with ID {checkpoint_id}")

    async def list_checkpoints(self, *, workflow_name: str) -> list[WorkflowCheckpoint]:
        """List checkpoint objects for a given workflow name."""
        return [cp for cp in self._checkpoints.values() if cp.workflow_name == workflow_name]

    async def delete(self, checkpoint_id: CheckpointID) -> bool:
        """Delete a checkpoint by ID."""
        if checkpoint_id in self._checkpoints:
            del self._checkpoints[checkpoint_id]
            logger.debug(f"Deleted checkpoint {checkpoint_id} from memory")
            return True
        return False

    async def get_latest(self, *, workflow_name: str) -> WorkflowCheckpoint | None:
        """Get the latest checkpoint for a given workflow name."""
        checkpoints = [cp for cp in self._checkpoints.values() if cp.workflow_name == workflow_name]
        if not checkpoints:
            return None
        latest_checkpoint = max(checkpoints, key=lambda cp: datetime.fromisoformat(cp.timestamp))
        logger.debug(f"Latest checkpoint for workflow {workflow_name} is {latest_checkpoint.checkpoint_id}")
        return latest_checkpoint

    async def list_checkpoint_ids(self, *, workflow_name: str) -> list[CheckpointID]:
        """List checkpoint IDs. If workflow_id is provided, filter by that workflow."""
        return [cp.checkpoint_id for cp in self._checkpoints.values() if cp.workflow_name == workflow_name]


class FileCheckpointStorage:
    """File-based checkpoint storage for persistence.

    This storage implements a hybrid approach where the checkpoint metadata and structure are
    stored in JSON format, while the actual state data (which may contain complex Python objects)
    is serialized using pickle and embedded as base64-encoded strings within the JSON. This allows
    for human-readable checkpoint files while preserving the ability to store complex Python objects.

    SECURITY WARNING: Checkpoints use pickle for data serialization. Only load checkpoints
    from trusted sources. Loading a malicious checkpoint file can execute arbitrary code.
    """

    def __init__(self, storage_path: str | Path):
        """Initialize the file storage."""
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Initialized file checkpoint storage at {self.storage_path}")

    def _validate_file_path(self, checkpoint_id: CheckpointID) -> Path:
        """Validate that a checkpoint ID resolves to a path within the storage directory.

        This can prevent someone from crafting a checkpoint ID that points to an arbitrary
        file on the filesystem.

        Args:
            checkpoint_id: The checkpoint ID to validate.

        Returns:
            The validated file path.

        Raises:
            WorkflowCheckpointException: If the checkpoint ID would resolve outside the storage directory.
        """
        file_path = (self.storage_path / f"{checkpoint_id}.json").resolve()
        if not file_path.is_relative_to(self.storage_path.resolve()):
            raise WorkflowCheckpointException(f"Invalid checkpoint ID: {checkpoint_id}")
        return file_path

    async def save(self, checkpoint: WorkflowCheckpoint) -> CheckpointID:
        """Save a checkpoint and return its ID.

        Args:
            checkpoint: The WorkflowCheckpoint object to save.

        Returns:
            The unique ID of the saved checkpoint.
        """
        from ._checkpoint_encoding import encode_checkpoint_value

        file_path = self._validate_file_path(checkpoint.checkpoint_id)
        checkpoint_dict = checkpoint.to_dict()
        encoded_checkpoint = encode_checkpoint_value(checkpoint_dict)

        def _write_atomic() -> None:
            tmp_path = file_path.with_suffix(".json.tmp")
            with open(tmp_path, "w") as f:
                json.dump(encoded_checkpoint, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, file_path)

        await asyncio.to_thread(_write_atomic)

        logger.info(f"Saved checkpoint {checkpoint.checkpoint_id} to {file_path}")
        return checkpoint.checkpoint_id

    async def load(self, checkpoint_id: CheckpointID) -> WorkflowCheckpoint:
        """Load a checkpoint by ID.

        Args:
            checkpoint_id: The unique ID of the checkpoint to load.

        Returns:
            The WorkflowCheckpoint object corresponding to the given ID.

        Raises:
            WorkflowCheckpointException: If no checkpoint with the given ID exists,
                or if checkpoint decoding fails.
        """
        file_path = self._validate_file_path(checkpoint_id)

        if not file_path.exists():
            raise WorkflowCheckpointException(f"No checkpoint found with ID {checkpoint_id}")

        def _read() -> dict[str, Any]:
            with open(file_path) as f:
                return json.load(f)  # type: ignore[no-any-return]

        encoded_checkpoint = await asyncio.to_thread(_read)

        from ._checkpoint_encoding import decode_checkpoint_value

        try:
            decoded_checkpoint_dict = decode_checkpoint_value(encoded_checkpoint)
        except WorkflowCheckpointException:
            raise
        checkpoint = WorkflowCheckpoint.from_dict(decoded_checkpoint_dict)
        logger.info(f"Loaded checkpoint {checkpoint_id} from {file_path}")
        return checkpoint

    async def list_checkpoints(self, *, workflow_name: str) -> list[WorkflowCheckpoint]:
        """List checkpoint objects for a given workflow name.

        Args:
            workflow_name: The name of the workflow to list checkpoints for.

        Returns:
            A list of WorkflowCheckpoint objects for the specified workflow name.
        """

        def _list_checkpoints() -> list[WorkflowCheckpoint]:
            checkpoints: list[WorkflowCheckpoint] = []
            for file_path in self.storage_path.glob("*.json"):
                try:
                    with open(file_path) as f:
                        encoded_checkpoint = json.load(f)
                        from ._checkpoint_encoding import decode_checkpoint_value

                        decoded_checkpoint_dict = decode_checkpoint_value(encoded_checkpoint)
                        checkpoint = WorkflowCheckpoint.from_dict(decoded_checkpoint_dict)
                    if checkpoint.workflow_name == workflow_name:
                        checkpoints.append(checkpoint)
                except Exception as e:
                    logger.warning(f"Failed to read checkpoint file {file_path}: {e}")
            return checkpoints

        return await asyncio.to_thread(_list_checkpoints)

    async def delete(self, checkpoint_id: CheckpointID) -> bool:
        """Delete a checkpoint by ID.

        Args:
            checkpoint_id: The unique ID of the checkpoint to delete.

        Returns:
            True if the checkpoint was successfully deleted, False if no checkpoint with the given ID exists.
        """
        file_path = self._validate_file_path(checkpoint_id)

        def _delete() -> bool:
            if file_path.exists():
                file_path.unlink()
                logger.info(f"Deleted checkpoint {checkpoint_id} from {file_path}")
                return True
            return False

        return await asyncio.to_thread(_delete)

    async def get_latest(self, *, workflow_name: str) -> WorkflowCheckpoint | None:
        """Get the latest checkpoint for a given workflow name.

        Args:
            workflow_name: The name of the workflow to get the latest checkpoint for.

        Returns:
            The latest WorkflowCheckpoint object for the specified workflow name, or None if no checkpoints exist.
        """
        checkpoints = await self.list_checkpoints(workflow_name=workflow_name)
        if not checkpoints:
            return None
        latest_checkpoint = max(checkpoints, key=lambda cp: datetime.fromisoformat(cp.timestamp))
        logger.debug(f"Latest checkpoint for workflow {workflow_name} is {latest_checkpoint.checkpoint_id}")
        return latest_checkpoint

    async def list_checkpoint_ids(self, *, workflow_name: str) -> list[CheckpointID]:
        """List checkpoint IDs for a given workflow name.

        Args:
            workflow_name: The name of the workflow to list checkpoint IDs for.

        Returns:
            A list of checkpoint IDs for the specified workflow name.
        """

        def _list_ids() -> list[CheckpointID]:
            checkpoint_ids: list[CheckpointID] = []
            for file_path in self.storage_path.glob("*.json"):
                try:
                    with open(file_path) as f:
                        data = json.load(f)
                    if data.get("workflow_name") == workflow_name:
                        checkpoint_ids.append(data.get("checkpoint_id", file_path.stem))
                except Exception as e:
                    logger.warning(f"Failed to read checkpoint file {file_path}: {e}")
            return checkpoint_ids

        return await asyncio.to_thread(_list_ids)
