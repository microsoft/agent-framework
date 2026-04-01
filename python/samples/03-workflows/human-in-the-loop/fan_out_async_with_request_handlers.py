# Copyright (c) Microsoft. All rights reserved.

"""
Sample: Fan-out Async + HITL with request_handlers parameter

Demonstrates automatic HITL request handling in fan-out workflows using the
request_handlers parameter. Handlers are dispatched inline as asyncio tasks
when request_info events are emitted during execution. The runner waits for
outstanding handler tasks before declaring convergence, so handler responses
are processed in subsequent supersteps within the same workflow run.

Usage:
    request_handlers = {
        ReviewRequest: handle_review,
        ApprovalRequest: handle_approval,
    }

    result = await workflow.run(
        initial_data,
        request_handlers=request_handlers,
    )
"""

import asyncio
import time
from dataclasses import dataclass

from agent_framework import (
    Executor,
    WorkflowBuilder,
    WorkflowContext,
    handler,
    response_handler,
)

_start_time: float = 0.0


def _ts() -> str:
    """Return elapsed seconds since workflow start."""
    return f"{time.monotonic() - _start_time:.1f}s"


@dataclass
class AnalysisData:
    """Initial data for analysis."""

    task: str
    data: str


@dataclass
class DataPacket:
    """Data flowing through the async processor."""

    iteration: int
    content: str
    analysis: str = ""


@dataclass
class ReviewRequest:
    """Request sent to human reviewer."""

    packet: DataPacket
    analysis: str
    prompt: str = "Please review the analysis and provide feedback"


class Analyzer(Executor):
    def __init__(self, id: str = "analyzer"):
        super().__init__(id)

    @handler
    async def start_analysis(
        self,
        data: AnalysisData,
        ctx: WorkflowContext[DataPacket, DataPacket],
    ) -> None:
        packet = DataPacket(
            iteration=0,
            content=data.data,
            analysis=f"Starting {data.task}...",
        )
        await ctx.send_message(packet)


class AsyncProcessor(Executor):
    """Async branch: loops and processes data."""

    def __init__(self, id: str = "processor"):
        super().__init__(id)
        self.iteration_count = 0

    @handler
    async def process_data(
        self,
        packet: DataPacket,
        ctx: WorkflowContext[DataPacket, DataPacket],
    ) -> None:
        self.iteration_count += 1
        await asyncio.sleep(0.5)
        analysis = f"Iteration {self.iteration_count}: {packet.content[:50]}... processed"
        print(f"  [{_ts()}] Processor: iteration {self.iteration_count}/10 complete")

        if self.iteration_count < 10:
            updated_packet = DataPacket(
                iteration=self.iteration_count,
                content=packet.content,
                analysis=analysis,
            )
            await ctx.send_message(updated_packet)
        else:
            # Stop sending to break the self-loop. Use yield_output for final result.
            print(f"  [{_ts()}] Processor: DONE after {self.iteration_count} iterations")
            await ctx.yield_output(
                DataPacket(iteration=self.iteration_count, content=packet.content, analysis=analysis)
            )


class Reviewer(Executor):
    """HITL branch: requests external feedback."""

    def __init__(self, id: str = "reviewer"):
        super().__init__(id)

    @handler
    async def review_data(
        self,
        packet: DataPacket,
        ctx: WorkflowContext[str, str],
    ) -> None:
        review_request = ReviewRequest(
            packet=packet,
            analysis=packet.analysis or "No analysis yet",
            prompt=f"Please review iteration {packet.iteration}",
        )

        await ctx.request_info(
            request_data=review_request,
            response_type=str,
        )

    @response_handler
    async def handle_review_feedback(
        self,
        original_request: ReviewRequest,
        feedback: str,
        ctx: WorkflowContext[str],
    ) -> None:
        print(f"  [{_ts()}] Reviewer: response_handler invoked with feedback")
        result = f"Review feedback processed: {feedback}"
        await ctx.send_message(result)


class FinalAggregator(Executor):
    def __init__(self, id: str = "aggregator"):
        super().__init__(id)
        self.results: list[str] = []

    @handler
    async def aggregate(
        self,
        message: DataPacket | str,
        ctx: WorkflowContext[str],
    ) -> None:
        self.results.append(str(message))

        if len(self.results) >= 2:
            summary = "=== WORKFLOW COMPLETE ===\n"
            summary += "Results from async path: " + str(self.results[0]) + "\n"
            summary += "Results from HITL path: " + str(self.results[1])
            await ctx.send_message(summary)


# ============================================================================
# Response Handlers (External)
# ============================================================================
# These are registered via request_handlers dict, not as executor methods.
# They are dispatched inline as asyncio tasks when request_info events are emitted.


async def handle_review(request: ReviewRequest) -> str:
    """Handle external review request.

    Dispatched as an asyncio task when the Reviewer emits a request_info
    with ReviewRequest type. The response is submitted back to the workflow
    and processed in a subsequent superstep.
    """
    print(f"  [{_ts()}] Handler: STARTED - reviewing iteration {request.packet.iteration}")

    # Simulate slow external API call (e.g., LLM inference, human approval system)
    await asyncio.sleep(3.0)

    feedback = "Analysis looks good. Continue processing."
    print(f"  [{_ts()}] Handler: DONE - returning feedback")

    return feedback


# ============================================================================
# Main
# ============================================================================


async def main() -> None:
    print("=" * 80)
    print("HITL: request_handlers parameter in workflow.run()")
    print("=" * 80)

    # Create executors
    analyzer = Analyzer()
    processor = AsyncProcessor()
    reviewer = Reviewer()
    aggregator = FinalAggregator()

    # Build workflow: processor self-loops, both branches feed into aggregator
    workflow = (
        WorkflowBuilder(start_executor=analyzer)
        .add_edge(analyzer, processor)
        .add_edge(analyzer, reviewer)
        .add_edge(processor, processor)  # self-loop for async processing
        .add_edge(processor, aggregator)
        .add_edge(reviewer, aggregator)
        .build()
    )

    initial_data = AnalysisData(
        task="document analysis",
        data="Sample document to process",
    )

    # ========================================================================
    # THE CLEAN API
    # ========================================================================
    # Define external response handlers (type-based dispatch)
    request_handlers = {
        ReviewRequest: handle_review,
        # Can add more: ApprovalRequest: handle_approval, etc.
    }

    global _start_time
    _start_time = time.monotonic()

    print(f"\n[{_ts()}] Start: {initial_data.task}")

    # Run workflow with automatic response handling (inline dispatch)
    # Handlers are dispatched as asyncio tasks when request_info events are emitted
    # Responses are injected back and processed in subsequent supersteps
    result = await workflow.run(
        initial_data,
        request_handlers=request_handlers,
    )

    elapsed = time.monotonic() - _start_time

    # Display results
    print(f"\n[{_ts()}] Final state: {result.get_final_state()}")
    print(f"  Total time: {elapsed:.1f}s")
    print(f"  Total events: {len(result)}")
    outputs = result.get_outputs()
    if outputs:
        print(f"Outputs ({len(outputs)}):")
        for output in outputs:
            print(f"  - {output}")

    """
    Sample Output:

    [0.0s] Start: document analysis

    [0.0s] Handler: STARTED - reviewing iteration 0
    [0.5s] Processor: iteration 1/10 complete
    [1.1s] Processor: iteration 2/10 complete
    [1.6s] Processor: iteration 3/10 complete
    [2.2s] Processor: iteration 4/10 complete
    [2.7s] Processor: iteration 5/10 complete
    [3.0s] Handler: DONE - returning feedback
    [3.3s] Processor: iteration 6/10 complete
    [3.3s] Reviewer: response_handler invoked with feedback
    [3.8s] Processor: iteration 7/10 complete
    [4.4s] Processor: iteration 8/10 complete
    [4.9s] Processor: iteration 9/10 complete
    [5.5s] Processor: iteration 10/10 complete
    [5.5s] Processor: DONE after 10 iterations

    [5.6s] Final state: WorkflowRunState.IDLE
    Total time: 5.6s
    Total events: 70
    Outputs (1):
    - DataPacket(iteration=10, content='Sample document to process', analysis='Iteration 10: Sample document to process... processed')
    """  # noqa: E501


if __name__ == "__main__":
    asyncio.run(main())
