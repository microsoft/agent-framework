# Copyright (c) Microsoft. All rights reserved.

"""
Tests for workflow request_handlers parameter.

Verifies automatic HITL request handling: type-based dispatch, concurrent execution,
error handling, parameter validation, and inline handler dispatch.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

import pytest

from agent_framework import (
    Executor,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowRunState,
    handler,
    response_handler,
)

# ---------------------------------------------------------------------------
# Shared request / data types
# ---------------------------------------------------------------------------


@dataclass
class ReviewRequest:
    """Request type for review."""

    id: str
    data: str


@dataclass
class ApprovalRequest:
    """Request type for approval."""

    id: str
    task: str


@dataclass
class UnknownRequest:
    """Request type with no registered handler."""

    id: str


# ---------------------------------------------------------------------------
# Executors
# ---------------------------------------------------------------------------


class ReviewerExecutor(Executor):
    """Requests a review and records whether the response was processed."""

    def __init__(self):
        super().__init__("reviewer")
        self.feedback_received: bool = False
        self.feedback_value: str | None = None

    @handler
    async def start(self, message: str, ctx: WorkflowContext) -> None:
        request = ReviewRequest(id="r1", data=f"Review: {message}")
        await ctx.request_info(request_data=request, response_type=str)

    @response_handler
    async def on_response(
        self,
        original_request: ReviewRequest,
        response: str,
        ctx: WorkflowContext[str],
    ) -> None:
        self.feedback_received = True
        self.feedback_value = response
        await ctx.send_message(f"review_done:{response}")


class ApproverExecutor(Executor):
    """Requests approval and records whether the response was processed."""

    def __init__(self):
        super().__init__("approver")
        self.approval_received: bool = False
        self.approval_value: str | None = None

    @handler
    async def start(self, message: str, ctx: WorkflowContext) -> None:
        request = ApprovalRequest(id="a1", task=f"Approve: {message}")
        await ctx.request_info(request_data=request, response_type=str)

    @response_handler
    async def on_response(
        self,
        original_request: ApprovalRequest,
        response: str,
        ctx: WorkflowContext[str],
    ) -> None:
        self.approval_received = True
        self.approval_value = response
        await ctx.send_message(f"approval_done:{response}")


class NoneResponseExecutor(Executor):
    """Requests info expecting a None response (valid value, not 'no response')."""

    def __init__(self):
        super().__init__("none_requester")
        self.handler_invoked: bool = False
        self.received_value: Any = "NOT_SET"

    @handler
    async def start(self, message: str, ctx: WorkflowContext) -> None:
        request = ReviewRequest(id="n1", data="needs-none")
        # Allow None as a valid response type
        await ctx.request_info(request_data=request, response_type=str | None)

    @response_handler
    async def on_response(
        self,
        original_request: ReviewRequest,
        response: str | None,
        ctx: WorkflowContext[str],
    ) -> None:
        self.handler_invoked = True
        self.received_value = response


class UnknownRequestExecutor(Executor):
    """Emits a request type with no handler registered."""

    def __init__(self):
        super().__init__("unknown_requester")

    @handler
    async def start(self, message: str, ctx: WorkflowContext) -> None:
        request = UnknownRequest(id="u1")
        await ctx.request_info(request_data=request, response_type=str)

    @response_handler
    async def on_response(
        self,
        original_request: UnknownRequest,
        response: str,
        ctx: WorkflowContext[str],
    ) -> None:
        pass  # Should never be reached


class SimpleExecutor(Executor):
    """Executor that just passes messages through without requesting info."""

    def __init__(self):
        super().__init__("simple")

    @handler
    async def start(self, message: str, ctx: WorkflowContext[str]) -> None:
        await ctx.send_message(f"echo:{message}")


class CollectorExecutor(Executor):
    """Collects messages for verification."""

    def __init__(self):
        super().__init__("collector")
        self.collected: list[str] = []

    @handler
    async def collect(self, message: str, ctx: WorkflowContext) -> None:
        self.collected.append(message)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestResponseHandlers:
    async def test_single_handler_submits_response(self):
        """Handler response is submitted back and the executor's response_handler runs."""
        reviewer = ReviewerExecutor()
        collector = CollectorExecutor()
        workflow = WorkflowBuilder(start_executor=reviewer).add_edge(reviewer, collector).build()

        async def handle_review(request: ReviewRequest) -> str:
            return "lgtm"

        result = await workflow.run(
            "test_msg",
            request_handlers={ReviewRequest: handle_review},
        )

        assert reviewer.feedback_received is True
        assert reviewer.feedback_value == "lgtm"
        assert result.get_final_state() == WorkflowRunState.IDLE
        # Collector should have received the message from the response handler
        assert any("review_done:lgtm" in msg for msg in collector.collected)

    async def test_multiple_handlers_dispatched_by_type(self):
        """Two different request types are dispatched to their respective handlers."""
        reviewer = ReviewerExecutor()
        approver = ApproverExecutor()
        collector = CollectorExecutor()

        # Use a dispatcher to fan out to both executors
        class Dispatcher(Executor):
            def __init__(self):
                super().__init__("dispatcher")

            @handler
            async def start(self, message: str, ctx: WorkflowContext) -> None:
                await ctx.send_message(message)

        dispatcher = Dispatcher()
        workflow = (
            WorkflowBuilder(start_executor=dispatcher)
            .add_edge(dispatcher, reviewer)
            .add_edge(dispatcher, approver)
            .add_edge(reviewer, collector)
            .add_edge(approver, collector)
            .build()
        )

        async def handle_review(request: ReviewRequest) -> str:
            return "review_ok"

        async def handle_approval(request: ApprovalRequest) -> str:
            return "approved"

        result = await workflow.run(
            "multi_test",
            request_handlers={
                ReviewRequest: handle_review,
                ApprovalRequest: handle_approval,
            },
        )

        assert reviewer.feedback_received is True
        assert reviewer.feedback_value == "review_ok"
        assert approver.approval_received is True
        assert approver.approval_value == "approved"
        assert result.get_final_state() == WorkflowRunState.IDLE

    async def test_handler_returning_none_is_valid_response(self):
        """A handler that returns None should still submit the response (sentinel fix)."""
        none_exec = NoneResponseExecutor()
        workflow = WorkflowBuilder(start_executor=none_exec).build()

        async def handle_returning_none(request: ReviewRequest) -> None:
            return None

        result = await workflow.run(
            "test_none",
            request_handlers={ReviewRequest: handle_returning_none},
        )

        # The handler matched and returned None — that None should be submitted
        assert none_exec.handler_invoked is True
        assert none_exec.received_value is None
        assert result.get_final_state() == WorkflowRunState.IDLE

    async def test_handler_exception_leaves_request_pending(self, caplog):
        """A handler that raises keeps the request pending and logs an error."""
        reviewer = ReviewerExecutor()
        workflow = WorkflowBuilder(start_executor=reviewer).build()

        async def failing_handler(request: ReviewRequest) -> str:
            raise RuntimeError("handler boom")

        with caplog.at_level(logging.ERROR):
            result = await workflow.run(
                "fail_test",
                request_handlers={ReviewRequest: failing_handler},
            )

        assert reviewer.feedback_received is False
        assert result.get_final_state() == WorkflowRunState.IDLE_WITH_PENDING_REQUESTS
        assert "handler boom" in caplog.text
        assert "ReviewRequest" in caplog.text

    async def test_handler_type_mismatch_leaves_request_pending(self, caplog):
        """A handler returning wrong type should not drop the pending request."""
        reviewer = ReviewerExecutor()
        workflow = WorkflowBuilder(start_executor=reviewer).build()

        async def wrong_type_handler(request: ReviewRequest) -> int:
            return 123

        with caplog.at_level(logging.ERROR):
            result1 = await workflow.run(
                "bad_type_test",
                request_handlers={ReviewRequest: wrong_type_handler},
            )

        assert reviewer.feedback_received is False
        assert result1.get_final_state() == WorkflowRunState.IDLE_WITH_PENDING_REQUESTS
        assert "Response type mismatch" in caplog.text

        # Pending request should still be recoverable via manual response submission.
        request_events = result1.get_request_info_events()
        assert len(request_events) == 1

        result2 = await workflow.run(
            responses={request_events[0].request_id: "manual_retry"},
        )
        assert reviewer.feedback_received is True
        assert reviewer.feedback_value == "manual_retry"
        assert result2.get_final_state() == WorkflowRunState.IDLE

    async def test_unmatched_type_logs_warning(self, caplog):
        """A request type with no matching handler logs a warning and stays pending."""
        unknown_exec = UnknownRequestExecutor()
        workflow = WorkflowBuilder(start_executor=unknown_exec).build()

        # Register a handler for a *different* type
        async def handle_review(request: ReviewRequest) -> str:
            return "unused"

        with caplog.at_level(logging.WARNING):
            result = await workflow.run(
                "unknown_test",
                request_handlers={ReviewRequest: handle_review},
            )

        assert result.get_final_state() == WorkflowRunState.IDLE_WITH_PENDING_REQUESTS
        assert "UnknownRequest" in caplog.text
        assert "ReviewRequest" in caplog.text

    async def test_stream_true_with_handlers_works(self):
        """stream=True + request_handlers works with inline dispatch."""
        reviewer = ReviewerExecutor()
        collector = CollectorExecutor()
        workflow = WorkflowBuilder(start_executor=reviewer).add_edge(reviewer, collector).build()

        async def handle_review(request: ReviewRequest) -> str:
            return "stream_lgtm"

        events = []
        stream = workflow.run(
            "stream_test",
            stream=True,
            request_handlers={ReviewRequest: handle_review},
        )
        async for event in stream:
            events.append(event)
        result = await stream.get_final_response()

        assert reviewer.feedback_received is True
        assert reviewer.feedback_value == "stream_lgtm"
        assert result.get_final_state() == WorkflowRunState.IDLE
        assert any("review_done:stream_lgtm" in msg for msg in collector.collected)

    async def test_responses_with_handlers_raises(self):
        """request_handlers + responses raises ValueError immediately."""
        reviewer = ReviewerExecutor()
        workflow = WorkflowBuilder(start_executor=reviewer).build()

        async def handle_review(request: ReviewRequest) -> str:
            return "x"

        with pytest.raises(ValueError, match="request_handlers.*responses"):
            await workflow.run(
                responses={"some_id": "value"},
                request_handlers={ReviewRequest: handle_review},
            )

    async def test_no_request_info_handlers_unused(self):
        """Handlers registered but no request_info events — workflow completes normally."""
        simple = SimpleExecutor()
        collector = CollectorExecutor()
        workflow = WorkflowBuilder(start_executor=simple).add_edge(simple, collector).build()

        async def handle_review(request: ReviewRequest) -> str:
            return "unused"

        result = await workflow.run(
            "hello",
            request_handlers={ReviewRequest: handle_review},
        )

        assert result.get_final_state() == WorkflowRunState.IDLE
        assert len(result.get_request_info_events()) == 0

    async def test_none_handlers_preserves_behavior(self):
        """request_handlers=None preserves original IDLE_WITH_PENDING_REQUESTS state."""
        reviewer = ReviewerExecutor()
        workflow = WorkflowBuilder(start_executor=reviewer).build()

        result = await workflow.run("test_default", request_handlers=None)

        assert reviewer.feedback_received is False
        assert result.get_final_state() == WorkflowRunState.IDLE_WITH_PENDING_REQUESTS

    async def test_handlers_run_concurrently(self):
        """Two 200ms handlers complete in under 350ms (proving concurrency)."""
        reviewer = ReviewerExecutor()
        approver = ApproverExecutor()

        class Dispatcher(Executor):
            def __init__(self):
                super().__init__("dispatcher")

            @handler
            async def start(self, message: str, ctx: WorkflowContext) -> None:
                await ctx.send_message(message)

        dispatcher = Dispatcher()
        workflow = (
            WorkflowBuilder(start_executor=dispatcher)
            .add_edge(dispatcher, reviewer)
            .add_edge(dispatcher, approver)
            .build()
        )

        async def slow_review(request: ReviewRequest) -> str:
            await asyncio.sleep(0.2)
            return "reviewed"

        async def slow_approval(request: ApprovalRequest) -> str:
            await asyncio.sleep(0.2)
            return "approved"

        start = time.monotonic()
        await workflow.run(
            "concurrent_test",
            request_handlers={
                ReviewRequest: slow_review,
                ApprovalRequest: slow_approval,
            },
        )
        elapsed = time.monotonic() - start

        # Two 200ms handlers running concurrently should be well under 500ms
        # (generous margin for CI/test overhead; sequential would be ~400ms+)
        assert elapsed < 0.5, f"Expected < 500ms, got {elapsed * 1000:.0f}ms"

    async def test_events_include_request_and_response_handling(self):
        """Result contains request_info events and executor events from response processing."""
        reviewer = ReviewerExecutor()
        collector = CollectorExecutor()
        workflow = WorkflowBuilder(start_executor=reviewer).add_edge(reviewer, collector).build()

        async def handle_review(request: ReviewRequest) -> str:
            return "feedback"

        result = await workflow.run(
            "merge_test",
            request_handlers={ReviewRequest: handle_review},
        )

        # Should have produced request_info events
        request_events = result.get_request_info_events()
        assert len(request_events) >= 1
        assert isinstance(request_events[0].data, ReviewRequest)

        # Response handler should have triggered executor events (reviewer response handler ran)
        executor_invoked_events = [e for e in result if e.type == "executor_invoked"]
        assert len(executor_invoked_events) >= 2  # Initial + response handling

        # Final state should be IDLE (response was processed)
        assert result.get_final_state() == WorkflowRunState.IDLE

    async def test_handler_with_looping_branch(self):
        """Fan-out with self-looping branch + HITL handler: handler dispatches while loop runs."""

        @dataclass
        class LoopMessage:
            iteration: int
            content: str

        class LoopingProcessor(Executor):
            """Loops a fixed number of times via self-send. Stops by not sending."""

            def __init__(self):
                super().__init__("looper")
                self.iteration_count = 0

            @handler
            async def process(self, message: LoopMessage, ctx: WorkflowContext[LoopMessage]) -> None:
                self.iteration_count += 1
                if self.iteration_count < 3:
                    await ctx.send_message(LoopMessage(iteration=self.iteration_count, content="processing"))

        class HITLExecutor(Executor):
            """Requests info from external handler."""

            def __init__(self):
                super().__init__("hitl")
                self.response_received = False
                self.response_value: str | None = None

            @handler
            async def start(self, message: LoopMessage, ctx: WorkflowContext) -> None:
                request = ReviewRequest(id="hitl_req", data=f"Review: {message.content}")
                await ctx.request_info(request_data=request, response_type=str)

            @response_handler
            async def on_response(
                self,
                original_request: ReviewRequest,
                response: str,
                ctx: WorkflowContext[str],
            ) -> None:
                self.response_received = True
                self.response_value = response

        class FanOutDispatcher(Executor):
            def __init__(self):
                super().__init__("fanout")

            @handler
            async def start(self, message: str, ctx: WorkflowContext[LoopMessage]) -> None:
                await ctx.send_message(LoopMessage(iteration=0, content=message))

        fanout = FanOutDispatcher()
        looper = LoopingProcessor()
        hitl = HITLExecutor()

        workflow = (
            WorkflowBuilder(start_executor=fanout)
            .add_edge(fanout, looper)
            .add_edge(fanout, hitl)
            .add_edge(looper, looper)  # self-loop (stops when no message sent)
            .build()
        )

        async def handle_review(request: ReviewRequest) -> str:
            await asyncio.sleep(0.1)  # Simulate async work
            return "approved_by_handler"

        result = await workflow.run(
            "fan_out_test",
            request_handlers={ReviewRequest: handle_review},
        )

        # Looping branch completed its iterations
        assert looper.iteration_count == 3

        # HITL handler was dispatched and response processed
        assert hitl.response_received is True
        assert hitl.response_value == "approved_by_handler"

        # Final state should be IDLE (all branches complete, all requests handled)
        assert result.get_final_state() == WorkflowRunState.IDLE


class TestBuilderLevelResponseHandlers:
    """Tests for request_handlers passed via WorkflowBuilder constructor."""

    async def test_builder_handlers_used_as_default(self):
        """Builder-level request_handlers are used when run() has none."""
        reviewer = ReviewerExecutor()
        collector = CollectorExecutor()

        async def handle_review(request: ReviewRequest) -> str:
            return "builder_lgtm"

        workflow = (
            WorkflowBuilder(
                start_executor=reviewer,
                request_handlers={ReviewRequest: handle_review},
            )
            .add_edge(reviewer, collector)
            .build()
        )

        result = await workflow.run("test_builder")

        assert reviewer.feedback_received is True
        assert reviewer.feedback_value == "builder_lgtm"
        assert result.get_final_state() == WorkflowRunState.IDLE
        assert any("review_done:builder_lgtm" in msg for msg in collector.collected)

    async def test_run_level_overrides_builder(self):
        """run(request_handlers=...) overrides builder-level handlers."""
        reviewer = ReviewerExecutor()
        collector = CollectorExecutor()

        async def builder_handler(request: ReviewRequest) -> str:
            return "from_builder"

        async def run_handler(request: ReviewRequest) -> str:
            return "from_run"

        workflow = (
            WorkflowBuilder(
                start_executor=reviewer,
                request_handlers={ReviewRequest: builder_handler},
            )
            .add_edge(reviewer, collector)
            .build()
        )

        result = await workflow.run(
            "test_override",
            request_handlers={ReviewRequest: run_handler},
        )

        assert reviewer.feedback_value == "from_run"
        assert result.get_final_state() == WorkflowRunState.IDLE

    async def test_validation_rejects_unknown_type(self):
        """Builder rejects request_handlers with types not in any @response_handler."""
        reviewer = ReviewerExecutor()

        async def handle_unknown(request: UnknownRequest) -> str:
            return "x"

        with pytest.raises(ValueError, match="UnknownRequest.*does not match"):
            WorkflowBuilder(
                start_executor=reviewer,
                request_handlers={UnknownRequest: handle_unknown},
            ).build()

    async def test_validation_passes_for_known_types(self):
        """Builder accepts request_handlers matching executor @response_handler types."""
        reviewer = ReviewerExecutor()
        approver = ApproverExecutor()

        async def handle_review(request: ReviewRequest) -> str:
            return "ok"

        async def handle_approval(request: ApprovalRequest) -> str:
            return "approved"

        # Should not raise — both types are declared via @response_handler on executors
        class Dispatcher(Executor):
            def __init__(self):
                super().__init__("dispatcher")

            @handler
            async def start(self, message: str, ctx: WorkflowContext) -> None:
                await ctx.send_message(message)

        dispatcher = Dispatcher()
        workflow = (
            WorkflowBuilder(
                start_executor=dispatcher,
                request_handlers={
                    ReviewRequest: handle_review,
                    ApprovalRequest: handle_approval,
                },
            )
            .add_edge(dispatcher, reviewer)
            .add_edge(dispatcher, approver)
            .build()
        )
        assert workflow is not None

    async def test_validation_partial_mismatch_rejected(self):
        """Builder rejects if any key is unknown, even if others are valid."""
        reviewer = ReviewerExecutor()

        async def handle_review(request: ReviewRequest) -> str:
            return "ok"

        async def handle_unknown(request: UnknownRequest) -> str:
            return "x"

        with pytest.raises(ValueError, match="UnknownRequest.*does not match"):
            WorkflowBuilder(
                start_executor=reviewer,
                request_handlers={
                    ReviewRequest: handle_review,
                    UnknownRequest: handle_unknown,
                },
            ).build()

    async def test_responses_bypass_builder_handlers(self):
        """run(responses=...) works even when builder has default request_handlers.

        Regression: without the fix, builder-level handlers would be treated as
        effective_handlers, causing _validate_run_params to raise ValueError
        ('Cannot provide both request_handlers and responses').
        """
        reviewer = ReviewerExecutor()
        collector = CollectorExecutor()

        async def failing_handler(request: ReviewRequest) -> str:
            raise RuntimeError("intentional failure")

        # Build with handlers that always fail — first run ends with pending request
        workflow = (
            WorkflowBuilder(
                start_executor=reviewer,
                request_handlers={ReviewRequest: failing_handler},
            )
            .add_edge(reviewer, collector)
            .build()
        )

        result1 = await workflow.run("first")
        assert result1.get_final_state() == WorkflowRunState.IDLE_WITH_PENDING_REQUESTS
        request_events = result1.get_request_info_events()
        assert len(request_events) == 1

        # Manual response submission should NOT conflict with builder-level handlers
        result2 = await workflow.run(responses={request_events[0].request_id: "manual_response"})
        assert reviewer.feedback_received is True
        assert reviewer.feedback_value == "manual_response"
        assert result2.get_final_state() == WorkflowRunState.IDLE
