# Copyright (c) Microsoft. All rights reserved.

"""Hosted workflow conversation checkpoint adapter."""

from __future__ import annotations

import copy
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from agent_framework import FileCheckpointStorage, WorkflowAgent
from azure.ai.agentserver.responses.models import MessageRole

AZURE_RESPONSES_MESSAGE_ROLE_TYPE = f"{MessageRole.__module__}:{MessageRole.__qualname__}"


def checkpoint_storage_for_context(root: str, context_id: str) -> FileCheckpointStorage:
    """Build a ``FileCheckpointStorage`` for a hosted response/conversation context.

    ``context_id`` originates from caller-controlled fields such as
    ``previous_response_id`` or from server-generated fields such as
    ``conversation_id`` / ``response_id``. In every case it must be treated as
    an untrusted single path segment: path separators, drive letters, parent
    references and similar would otherwise let the resulting directory escape
    the configured checkpoint root (CWE-22).
    """
    if not isinstance(context_id, str) or not context_id:
        raise RuntimeError("Invalid checkpoint context id: must be a non-empty string.")
    # Treat every hosted context id as one untrusted path segment. Do not URL-decode here:
    # hosting never decodes these ids before joining them, so encoded traversal markers
    # are accepted as literal directory names.
    if (
        "/" in context_id
        or "\\" in context_id
        or "\x00" in context_id
        or context_id.strip(".") == ""
        or os.path.isabs(context_id)
        or os.path.splitdrive(context_id)[0]
    ):
        raise RuntimeError(f"Invalid checkpoint context id: {context_id!r}")

    root_path = Path(root).resolve()
    storage_path = (root_path / context_id).resolve()
    if not storage_path.is_relative_to(root_path):
        raise RuntimeError(f"Invalid checkpoint context id: {context_id!r}")
    return FileCheckpointStorage(
        storage_path,
        # Hosted workflow checkpoints can persist Azure's role enum inside Message objects.
        allowed_checkpoint_types=[AZURE_RESPONSES_MESSAGE_ROLE_TYPE],
    )


_AZURE_RESPONSES_MESSAGE_ROLE_TYPE = AZURE_RESPONSES_MESSAGE_ROLE_TYPE
_checkpoint_storage_for_context = checkpoint_storage_for_context


@dataclass(frozen=True)
class HostedWorkflowConversationTurn:
    """Workflow agent instance and checkpoint resources for one hosted response turn."""

    agent: WorkflowAgent
    restore_context_id: str | None
    write_context_id: str
    restore_checkpoint_id: str | None
    restore_checkpoint_storage: FileCheckpointStorage | None
    write_checkpoint_storage: FileCheckpointStorage

    async def restore(self, *, stream: bool) -> None:
        """Restore the previous workflow checkpoint, if this turn has one."""
        if self.restore_checkpoint_id is None:
            return
        if self.restore_checkpoint_storage is None:  # pragma: no cover - defensive invariant
            raise RuntimeError("Restore checkpoint storage is not configured.")

        if stream:
            async for _ in self.agent.run(
                stream=True,
                checkpoint_id=self.restore_checkpoint_id,
                checkpoint_storage=self.restore_checkpoint_storage,
            ):
                pass
            return

        await self.agent.run(
            stream=False,
            checkpoint_id=self.restore_checkpoint_id,
            checkpoint_storage=self.restore_checkpoint_storage,
        )

    async def delete_not_latest_checkpoints(self, workflow_name: str) -> None:
        """Delete old checkpoints from this turn's write context."""
        latest_checkpoint = await self.write_checkpoint_storage.get_latest(workflow_name=workflow_name)
        if latest_checkpoint is None:
            return
        all_checkpoints = await self.write_checkpoint_storage.list_checkpoints(workflow_name=workflow_name)
        for checkpoint in all_checkpoints:
            if checkpoint.checkpoint_id != latest_checkpoint.checkpoint_id:
                await self.write_checkpoint_storage.delete(checkpoint.checkpoint_id)


def copy_workflow_agent_for_hosted_turn(agent: WorkflowAgent) -> WorkflowAgent:
    """Create a fresh workflow agent instance for a hosted workflow turn."""
    try:
        return copy.deepcopy(agent)
    except Exception as exc:
        raise RuntimeError(
            "Hosted workflow agents must be copyable so each response turn can run with isolated workflow state."
        ) from exc


class HostedWorkflowConversationAdapter:
    """Resolves checkpoint contexts for workflow agents hosted behind Responses."""

    def __init__(
        self,
        checkpoint_storage_root: str,
        workflow_agent_factory: Callable[[], WorkflowAgent],
    ) -> None:
        self._checkpoint_storage_root = checkpoint_storage_root
        self._workflow_agent_factory = workflow_agent_factory

    async def prepare_turn(
        self,
        *,
        response_id: str,
        previous_response_id: str | None,
        conversation_id: str | None,
    ) -> HostedWorkflowConversationTurn:
        """Prepare restore and write checkpoint storage for one hosted workflow turn.

        ``previous_response_id`` restores from the prior response and writes
        under the current response. ``conversation_id`` restores and writes
        under the same stable conversation context.
        """
        if previous_response_id is not None and conversation_id is not None:
            raise RuntimeError("Previous response ID cannot be used in conjunction with conversation ID.")

        restore_context_id = previous_response_id or conversation_id
        restore_checkpoint_id: str | None = None
        restore_checkpoint_storage: FileCheckpointStorage | None = None
        if restore_context_id is not None:
            restore_checkpoint_storage = checkpoint_storage_for_context(
                self._checkpoint_storage_root,
                restore_context_id,
            )

        write_context_id = conversation_id or response_id
        write_checkpoint_storage = checkpoint_storage_for_context(self._checkpoint_storage_root, write_context_id)

        agent = self._workflow_agent_factory()
        if not isinstance(agent, WorkflowAgent):
            raise RuntimeError("Workflow agent factory did not return a WorkflowAgent.")

        if restore_checkpoint_storage is not None:
            latest_checkpoint = await restore_checkpoint_storage.get_latest(workflow_name=agent.workflow.name)
            if latest_checkpoint is not None:
                restore_checkpoint_id = latest_checkpoint.checkpoint_id

        return HostedWorkflowConversationTurn(
            agent=agent,
            restore_context_id=restore_context_id,
            write_context_id=write_context_id,
            restore_checkpoint_id=restore_checkpoint_id,
            restore_checkpoint_storage=restore_checkpoint_storage,
            write_checkpoint_storage=write_checkpoint_storage,
        )
