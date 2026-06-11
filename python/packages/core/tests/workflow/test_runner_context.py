# Copyright (c) Microsoft. All rights reserved.

"""Tests for `InProcRunnerContext`."""

import pytest

from agent_framework import (
    InProcRunnerContext,
    WorkflowEvent,
    WorkflowMessage,
)


def _make_request_info_event(request_id: str, source_executor_id: str = "executor") -> WorkflowEvent[str]:
    return WorkflowEvent.request_info(
        request_id=request_id,
        source_executor_id=source_executor_id,
        request_data="please respond",
        response_type=str,
    )


class TestInProcRunnerContextResetForNewRun:
    """Verify `reset_for_new_run` clears per-run state, including pending request_info events."""

    async def test_reset_clears_pending_request_info_events(self) -> None:
        ctx = InProcRunnerContext()

        await ctx.add_request_info_event(_make_request_info_event("req-1"))
        await ctx.add_request_info_event(_make_request_info_event("req-2"))

        assert set((await ctx.get_pending_request_info_events()).keys()) == {"req-1", "req-2"}

        ctx.reset_for_new_run()

        assert await ctx.get_pending_request_info_events() == {}

    async def test_reset_clears_pending_request_info_events_when_already_empty(self) -> None:
        ctx = InProcRunnerContext()

        assert await ctx.get_pending_request_info_events() == {}

        ctx.reset_for_new_run()

        assert await ctx.get_pending_request_info_events() == {}

    async def test_reset_after_pending_event_blocks_response_correlation(self) -> None:
        """After `reset_for_new_run`, prior request ids must no longer correlate to a response."""
        ctx = InProcRunnerContext()
        await ctx.add_request_info_event(_make_request_info_event("req-1"))

        ctx.reset_for_new_run()

        with pytest.raises(ValueError, match="No pending request found for request_id: req-1"):
            await ctx.send_request_info_response("req-1", "answer")

    async def test_reset_clears_messages_events_and_streaming_flag(self) -> None:
        """Sanity-check the other state `reset_for_new_run` is documented to clear."""
        ctx = InProcRunnerContext()
        await ctx.send_message(WorkflowMessage(data="hello", source_id="executor"))
        await ctx.add_event(WorkflowEvent("status", data="running"))
        ctx.set_streaming(True)

        assert await ctx.has_messages() is True
        assert await ctx.has_events() is True
        assert ctx.is_streaming() is True

        ctx.reset_for_new_run()

        assert await ctx.has_messages() is False
        assert await ctx.has_events() is False
        assert ctx.is_streaming() is False
