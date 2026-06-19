# Copyright (c) Microsoft. All rights reserved.

"""Tests for hosted workflow conversation checkpoint planning."""

from __future__ import annotations

from pathlib import Path

import pytest
from agent_framework import (
    Content,
    Message,
    WorkflowAgent,
    WorkflowBuilder,
    WorkflowCheckpoint,
    WorkflowContext,
    executor,
)
from typing_extensions import Any

from agent_framework_foundry_hosting._hosted_workflow_conversation import (  # pyright: ignore[reportPrivateUsage]
    HostedWorkflowConversationAdapter,
    checkpoint_storage_for_context,
)


async def test_fresh_turn_writes_current_response_context(tmp_path: Path) -> None:
    adapter = _adapter(tmp_path)

    turn = await adapter.prepare_turn(
        response_id="resp-1",
        previous_response_id=None,
        conversation_id=None,
    )

    assert isinstance(turn.agent, WorkflowAgent)
    assert turn.restore_context_id is None
    assert turn.restore_checkpoint_id is None
    assert turn.restore_checkpoint_storage is None
    assert turn.write_context_id == "resp-1"
    assert turn.write_checkpoint_storage.storage_path == (tmp_path / "resp-1").resolve()


async def test_previous_response_id_turn_restores_previous_context_and_writes_current_response_context(
    tmp_path: Path,
) -> None:
    await _save_checkpoint(tmp_path, "resp-1", "ckpt-1")
    adapter = _adapter(tmp_path)

    turn = await adapter.prepare_turn(
        response_id="resp-2",
        previous_response_id="resp-1",
        conversation_id=None,
    )

    assert turn.restore_context_id == "resp-1"
    assert turn.restore_checkpoint_id == "ckpt-1"
    assert turn.restore_checkpoint_storage is not None
    assert turn.restore_checkpoint_storage.storage_path == (tmp_path / "resp-1").resolve()
    assert turn.write_context_id == "resp-2"
    assert turn.write_checkpoint_storage.storage_path == (tmp_path / "resp-2").resolve()


async def test_conversation_id_turn_restores_and_writes_same_stable_context(tmp_path: Path) -> None:
    await _save_checkpoint(tmp_path, "conv-alpha", "ckpt-1")
    adapter = _adapter(tmp_path)

    turn = await adapter.prepare_turn(
        response_id="resp-2",
        previous_response_id=None,
        conversation_id="conv-alpha",
    )

    assert turn.restore_context_id == "conv-alpha"
    assert turn.restore_checkpoint_id == "ckpt-1"
    assert turn.restore_checkpoint_storage is not None
    assert turn.restore_checkpoint_storage.storage_path == (tmp_path / "conv-alpha").resolve()
    assert turn.write_context_id == "conv-alpha"
    assert turn.write_checkpoint_storage.storage_path == (tmp_path / "conv-alpha").resolve()


async def test_previous_response_id_and_conversation_id_are_mutually_exclusive(tmp_path: Path) -> None:
    adapter = _adapter(tmp_path)

    with pytest.raises(RuntimeError, match="Previous response ID cannot be used in conjunction with conversation ID"):
        await adapter.prepare_turn(
            response_id="resp-2",
            previous_response_id="resp-1",
            conversation_id="conv-alpha",
        )


async def test_turn_prunes_old_checkpoints_from_write_context(tmp_path: Path) -> None:
    storage = checkpoint_storage_for_context(str(tmp_path), "conv-alpha")
    await storage.save(
        WorkflowCheckpoint(
            workflow_name="wf",
            graph_signature_hash="hash",
            checkpoint_id="ckpt-old",
            timestamp="2024-01-01T00:00:00+00:00",
        )
    )
    await storage.save(
        WorkflowCheckpoint(
            workflow_name="wf",
            graph_signature_hash="hash",
            checkpoint_id="ckpt-new",
            timestamp="2024-01-02T00:00:00+00:00",
        )
    )
    adapter = _adapter(tmp_path)
    turn = await adapter.prepare_turn(
        response_id="resp-1",
        previous_response_id=None,
        conversation_id="conv-alpha",
    )

    await turn.delete_not_latest_checkpoints("wf")

    checkpoint_ids = sorted(
        checkpoint.checkpoint_id
        for checkpoint in await turn.write_checkpoint_storage.list_checkpoints(workflow_name="wf")
    )
    assert checkpoint_ids == ["ckpt-new"]


async def test_adapter_uses_new_workflow_agent_for_each_turn(tmp_path: Path) -> None:
    created_agents: list[WorkflowAgent] = []

    def factory() -> WorkflowAgent:
        agent = _build_workflow_agent()
        created_agents.append(agent)
        return agent

    adapter = HostedWorkflowConversationAdapter(str(tmp_path), factory)

    first = await adapter.prepare_turn(
        response_id="resp-1",
        previous_response_id=None,
        conversation_id=None,
    )
    second = await adapter.prepare_turn(
        response_id="resp-2",
        previous_response_id=None,
        conversation_id=None,
    )

    assert first.agent is created_agents[0]
    assert second.agent is created_agents[1]
    assert first.agent is not second.agent


def _adapter(root: Path) -> HostedWorkflowConversationAdapter:
    return HostedWorkflowConversationAdapter(str(root), _build_workflow_agent)


def _build_workflow_agent() -> WorkflowAgent:
    @executor
    async def start(messages: list[Message], ctx: WorkflowContext[Any, Message]) -> None:
        await ctx.yield_output(Message(role="assistant", contents=[Content.from_text("ok")]))

    return WorkflowBuilder(name="wf", start_executor=start, output_from=[start]).build().as_agent()


async def _save_checkpoint(
    root: Path,
    context_id: str,
    checkpoint_id: str,
    *,
    workflow_name: str = "wf",
) -> None:
    storage = checkpoint_storage_for_context(str(root), context_id)
    await storage.save(
        WorkflowCheckpoint(
            workflow_name=workflow_name,
            graph_signature_hash="hash",
            checkpoint_id=checkpoint_id,
        )
    )
