# Copyright (c) Microsoft. All rights reserved.

"""Unit tests for workflow utility functions."""

from unittest.mock import Mock

import pytest
from agent_framework import WorkflowEvent, WorkflowMessage

from agent_framework_azurefunctions._context import CapturingRunnerContext


class TestCapturingRunnerContext:
    """Test suite for CapturingRunnerContext."""

    @pytest.fixture
    def context(self) -> CapturingRunnerContext:
        """Create a fresh CapturingRunnerContext for each test."""
        return CapturingRunnerContext()

    @pytest.mark.asyncio
    async def test_send_message_captures_message(self, context: CapturingRunnerContext) -> None:
        """Test that send_message captures messages correctly."""
        message = WorkflowMessage(data="test data", target_id="target_1", source_id="source_1")

        await context.send_message(message)

        messages = await context.drain_messages()
        assert "source_1" in messages
        assert len(messages["source_1"]) == 1
        assert messages["source_1"][0].data == "test data"

    @pytest.mark.asyncio
    async def test_send_multiple_messages_groups_by_source(self, context: CapturingRunnerContext) -> None:
        """Test that messages are grouped by source_id."""
        msg1 = WorkflowMessage(data="msg1", target_id="target", source_id="source_a")
        msg2 = WorkflowMessage(data="msg2", target_id="target", source_id="source_a")
        msg3 = WorkflowMessage(data="msg3", target_id="target", source_id="source_b")

        await context.send_message(msg1)
        await context.send_message(msg2)
        await context.send_message(msg3)

        messages = await context.drain_messages()
        assert len(messages["source_a"]) == 2
        assert len(messages["source_b"]) == 1

    @pytest.mark.asyncio
    async def test_drain_messages_clears_messages(self, context: CapturingRunnerContext) -> None:
        """Test that drain_messages clears the message store."""
        message = WorkflowMessage(data="test", target_id="t", source_id="s")
        await context.send_message(message)

        await context.drain_messages()  # First drain
        messages = await context.drain_messages()  # Second drain

        assert messages == {}

    @pytest.mark.asyncio
    async def test_has_messages_returns_correct_status(self, context: CapturingRunnerContext) -> None:
        """Test has_messages returns correct boolean."""
        assert await context.has_messages() is False

        await context.send_message(WorkflowMessage(data="test", target_id="t", source_id="s"))

        assert await context.has_messages() is True

    @pytest.mark.asyncio
    async def test_add_event_queues_event(self, context: CapturingRunnerContext) -> None:
        """Test that add_event queues events correctly."""
        event = WorkflowEvent("output", executor_id="exec_1", data="output")

        await context.add_event(event)

        events = await context.drain_events()
        assert len(events) == 1
        assert isinstance(events[0], WorkflowEvent)
        assert events[0].type == "output"
        assert events[0].data == "output"

    @pytest.mark.asyncio
    async def test_drain_events_clears_queue(self, context: CapturingRunnerContext) -> None:
        """Test that drain_events clears the event queue."""
        await context.add_event(WorkflowEvent("output", executor_id="e", data="test"))

        await context.drain_events()  # First drain
        events = await context.drain_events()  # Second drain

        assert events == []

    @pytest.mark.asyncio
    async def test_has_events_returns_correct_status(self, context: CapturingRunnerContext) -> None:
        """Test has_events returns correct boolean."""
        assert await context.has_events() is False

        await context.add_event(WorkflowEvent("output", executor_id="e", data="test"))

        assert await context.has_events() is True

    @pytest.mark.asyncio
    async def test_next_event_waits_for_event(self, context: CapturingRunnerContext) -> None:
        """Test that next_event returns queued events."""
        event = WorkflowEvent("output", executor_id="e", data="waited")
        await context.add_event(event)

        result = await context.next_event()

        assert result.data == "waited"

    def test_has_checkpointing_returns_false(self, context: CapturingRunnerContext) -> None:
        """Test that checkpointing is not supported."""
        assert context.has_checkpointing() is False

    def test_is_streaming_returns_false_by_default(self, context: CapturingRunnerContext) -> None:
        """Test streaming is disabled by default."""
        assert context.is_streaming() is False

    def test_set_streaming(self, context: CapturingRunnerContext) -> None:
        """Test setting streaming mode."""
        context.set_streaming(True)
        assert context.is_streaming() is True

        context.set_streaming(False)
        assert context.is_streaming() is False

    def test_set_workflow_id(self, context: CapturingRunnerContext) -> None:
        """Test setting workflow ID."""
        context.set_workflow_id("workflow-123")
        assert context._workflow_id == "workflow-123"

    @pytest.mark.asyncio
    async def test_reset_for_new_run_clears_state(self, context: CapturingRunnerContext) -> None:
        """Test that reset_for_new_run clears all state."""
        await context.send_message(WorkflowMessage(data="test", target_id="t", source_id="s"))
        await context.add_event(WorkflowEvent("output", executor_id="e", data="event"))
        context.set_streaming(True)

        context.reset_for_new_run()

        assert await context.has_messages() is False
        assert await context.has_events() is False
        assert context.is_streaming() is False

    @pytest.mark.asyncio
    async def test_create_checkpoint_raises_not_implemented(self, context: CapturingRunnerContext) -> None:
        """Test that checkpointing methods raise NotImplementedError."""
        from agent_framework._workflows._state import State

        with pytest.raises(NotImplementedError):
            await context.create_checkpoint("test_workflow", "abc123", State(), None, 1)

    @pytest.mark.asyncio
    async def test_load_checkpoint_raises_not_implemented(self, context: CapturingRunnerContext) -> None:
        """Test that load_checkpoint raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            await context.load_checkpoint("some-id")

    @pytest.mark.asyncio
    async def test_apply_checkpoint_raises_not_implemented(self, context: CapturingRunnerContext) -> None:
        """Test that apply_checkpoint raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            await context.apply_checkpoint(Mock())
