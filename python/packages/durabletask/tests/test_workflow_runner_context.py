# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for the durabletask workflow runner context."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

from unittest.mock import Mock

import pytest
from agent_framework import WorkflowEvent, WorkflowMessage
from agent_framework._workflows._state import State

from agent_framework_durabletask._workflows.runner_context import (
    HOST_METADATA_INSTANCE_ID,
    HOST_METADATA_REQUEST_PATH_PREFIX,
    HOST_METADATA_WORKFLOW_NAME,
    CapturingRunnerContext,
)


@pytest.fixture
def context() -> CapturingRunnerContext:
    return CapturingRunnerContext()


async def test_send_and_drain_messages(context: CapturingRunnerContext) -> None:
    message = WorkflowMessage(data="hello", target_id="target", source_id="source")

    await context.send_message(message)

    assert await context.has_messages() is True
    assert await context.drain_messages() == {"source": [message]}
    assert await context.has_messages() is False


async def test_events_can_be_queued_and_read(context: CapturingRunnerContext) -> None:
    event = WorkflowEvent("output", executor_id="exec", data="payload")

    await context.add_event(event)

    assert await context.has_events() is True
    assert await context.next_event() == event
    assert await context.has_events() is False


def test_checkpointing_is_unsupported(context: CapturingRunnerContext) -> None:
    storage = Mock()

    context.set_runtime_checkpoint_storage(storage)
    context.clear_runtime_checkpoint_storage()

    assert context.has_checkpointing() is False


async def test_checkpoint_methods_raise(context: CapturingRunnerContext) -> None:
    with pytest.raises(NotImplementedError, match="Checkpointing is not supported"):
        await context.create_checkpoint("workflow", "sig", State(), None, 1)

    with pytest.raises(NotImplementedError, match="Checkpointing is not supported"):
        await context.load_checkpoint("checkpoint-1")

    with pytest.raises(NotImplementedError, match="Checkpointing is not supported"):
        await context.apply_checkpoint(Mock())


def test_workflow_configuration_can_be_reset(context: CapturingRunnerContext) -> None:
    context.set_workflow_id("workflow-123")
    context.set_streaming(True)
    context.set_host_metadata({
        HOST_METADATA_INSTANCE_ID: "root-instance",
        HOST_METADATA_WORKFLOW_NAME: "wf",
        HOST_METADATA_REQUEST_PATH_PREFIX: "sub~0~",
    })
    context.set_yield_output_classifier(lambda executor_id: None if executor_id == "secret" else "intermediate")

    assert context.is_streaming() is True
    assert context.host_metadata == {
        HOST_METADATA_INSTANCE_ID: "root-instance",
        HOST_METADATA_WORKFLOW_NAME: "wf",
        HOST_METADATA_REQUEST_PATH_PREFIX: "sub~0~",
    }
    assert context.classify_yielded_output("secret") is None
    assert context.classify_yielded_output("visible") == "intermediate"

    context.reset_for_new_run()

    assert context.is_streaming() is False


async def test_request_info_events_are_tracked(context: CapturingRunnerContext) -> None:
    event = WorkflowEvent("request_info", executor_id="review", data={"question": "approve?"}, request_id="req-9")

    await context.add_request_info_event(event)

    assert await context.get_pending_request_info_events() == {"req-9": event}
    assert await context.drain_events() == [event]


async def test_request_info_response_is_not_supported(context: CapturingRunnerContext) -> None:
    with pytest.raises(NotImplementedError, match="orchestrator level"):
        await context.send_request_info_response("req-9", {"approved": True})
