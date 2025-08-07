# Copyright (c) Microsoft. All rights reserved.

import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

logger = logging.getLogger(__name__)


@dataclass
class WorkflowCheckpoint:
    """Represents a complete checkpoint of workflow state."""

    checkpoint_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    workflow_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Core workflow state
    messages: dict[str, list[dict[str, Any]]] = field(default_factory=dict)  # type: ignore[misc]
    events: list[dict[str, Any]] = field(default_factory=list)  # type: ignore[misc]
    shared_state: dict[str, Any] = field(default_factory=dict)  # type: ignore[misc]
    executor_states: dict[str, dict[str, Any]] = field(default_factory=dict)  # type: ignore[misc]

    # Runtime state
    iteration_count: int = 0
    max_iterations: int = 100

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)  # type: ignore[misc]
    version: str = "1.0"


class CheckpointStorage(Protocol):
    """Protocol for checkpoint storage backends."""

    def save_checkpoint(self, checkpoint: WorkflowCheckpoint) -> str:
        """Save a checkpoint and return its ID."""
        ...

    def load_checkpoint(self, checkpoint_id: str) -> WorkflowCheckpoint | None:
        """Load a checkpoint by ID."""
        ...

    def list_checkpoint_ids(self, workflow_id: str | None = None) -> list[str]:
        """List checkpoint IDs. If workflow_id is provided, filter by that workflow."""
        ...

    def list_checkpoints(self, workflow_id: str | None = None) -> list[WorkflowCheckpoint]:
        """List checkpoint objects. If workflow_id is provided, filter by that workflow."""
        ...

    def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """Delete a checkpoint by ID."""
        ...


class MemoryCheckpointStorage:
    """In-memory checkpoint storage for testing and development."""

    def __init__(self):
        """Initialize the memory storage."""
        self._checkpoints: dict[str, WorkflowCheckpoint] = {}

    def save_checkpoint(self, checkpoint: WorkflowCheckpoint) -> str:
        """Save a checkpoint and return its ID."""
        self._checkpoints[checkpoint.checkpoint_id] = checkpoint
        logger.debug(f"Saved checkpoint {checkpoint.checkpoint_id} to memory")
        return checkpoint.checkpoint_id

    def load_checkpoint(self, checkpoint_id: str) -> WorkflowCheckpoint | None:
        """Load a checkpoint by ID."""
        checkpoint = self._checkpoints.get(checkpoint_id)
        if checkpoint:
            logger.debug(f"Loaded checkpoint {checkpoint_id} from memory")
        return checkpoint

    def list_checkpoint_ids(self, workflow_id: str | None = None) -> list[str]:
        """List checkpoint IDs. If workflow_id is provided, filter by that workflow."""
        if workflow_id is None:
            return list(self._checkpoints.keys())
        return [cp.checkpoint_id for cp in self._checkpoints.values() if cp.workflow_id == workflow_id]

    def list_checkpoints(self, workflow_id: str | None = None) -> list[WorkflowCheckpoint]:
        """List checkpoint objects. If workflow_id is provided, filter by that workflow."""
        if workflow_id is None:
            return list(self._checkpoints.values())
        return [cp for cp in self._checkpoints.values() if cp.workflow_id == workflow_id]

    def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """Delete a checkpoint by ID."""
        if checkpoint_id in self._checkpoints:
            del self._checkpoints[checkpoint_id]
            logger.debug(f"Deleted checkpoint {checkpoint_id} from memory")
            return True
        return False


class FileCheckpointStorage:
    """File-based checkpoint storage for persistence."""

    def __init__(self, storage_path: str | Path):
        """Initialize the file storage."""
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Initialized file checkpoint storage at {self.storage_path}")

    def save_checkpoint(self, checkpoint: WorkflowCheckpoint) -> str:
        """Save a checkpoint and return its ID."""
        file_path = self.storage_path / f"{checkpoint.checkpoint_id}.json"
        checkpoint_dict = asdict(checkpoint)

        # Note: Using synchronous I/O for simplicity in this prototype
        # In production, consider using aiofiles for truly async I/O
        with open(file_path, "w") as f:
            json.dump(checkpoint_dict, f, indent=2, ensure_ascii=False)

        logger.info(f"Saved checkpoint {checkpoint.checkpoint_id} to {file_path}")
        return checkpoint.checkpoint_id

    def load_checkpoint(self, checkpoint_id: str) -> WorkflowCheckpoint | None:
        """Load a checkpoint by ID."""
        file_path = self.storage_path / f"{checkpoint_id}.json"

        if not file_path.exists():
            return None

        with open(file_path) as f:
            checkpoint_dict = json.load(f)

        checkpoint = WorkflowCheckpoint(**checkpoint_dict)
        logger.info(f"Loaded checkpoint {checkpoint_id} from {file_path}")
        return checkpoint

    def list_checkpoint_ids(self, workflow_id: str | None = None) -> list[str]:
        """List checkpoint IDs. If workflow_id is provided, filter by that workflow."""
        checkpoint_ids: list[str] = []

        for file_path in self.storage_path.glob("*.json"):
            try:
                with open(file_path) as f:
                    data = json.load(f)

                # If no workflow filter, include all checkpoints
                if workflow_id is None or data.get("workflow_id") == workflow_id:
                    checkpoint_ids.append(data.get("checkpoint_id", file_path.stem))
            except Exception as e:
                logger.warning(f"Failed to read checkpoint file {file_path}: {e}")

        return checkpoint_ids

    def list_checkpoints(self, workflow_id: str | None = None) -> list[WorkflowCheckpoint]:
        """List checkpoint objects. If workflow_id is provided, filter by that workflow."""
        checkpoints: list[WorkflowCheckpoint] = []

        for file_path in self.storage_path.glob("*.json"):
            try:
                with open(file_path) as f:
                    data = json.load(f)

                # If no workflow filter, include all checkpoints
                if workflow_id is None or data.get("workflow_id") == workflow_id:
                    checkpoint = WorkflowCheckpoint(**data)
                    checkpoints.append(checkpoint)
            except Exception as e:
                logger.warning(f"Failed to read checkpoint file {file_path}: {e}")

        return checkpoints

    def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """Delete a checkpoint by ID."""
        file_path = self.storage_path / f"{checkpoint_id}.json"

        if file_path.exists():
            file_path.unlink()
            logger.info(f"Deleted checkpoint {checkpoint_id} from {file_path}")
            return True

        return False
