# Copyright (c) Microsoft. All rights reserved.

"""Human-in-the-loop review pipeline using functional workflows.

Demonstrates ctx.request_info() for pausing the workflow to wait for
external input and resuming with run(responses={...}).

HITL works with or without @step. The difference is what happens on resume:
- Without @step: every function re-executes from the top (fine for cheap calls).
- With @step: completed functions return their saved result instantly.

This sample uses @step on write_draft() because it simulates an expensive
operation that shouldn't re-run just because the workflow was paused.
"""

import asyncio

from agent_framework import RunContext, WorkflowRunState, step, workflow


# @step saves the result. When the workflow resumes after the HITL pause,
# this returns its saved result instead of running the expensive operation again.
#
# In a real workflow you might call an agent here instead:
#   @step
#   async def write_draft(topic: str) -> str:
#       return (await writer_agent.run(f"Write a draft about: {topic}")).text
@step
async def write_draft(topic: str) -> str:
    """Simulate writing a draft — expensive, shouldn't re-run on resume."""
    print(f"  write_draft executing for '{topic}'")
    return f"Draft document about '{topic}': Lorem ipsum dolor sit amet..."


@step
async def revise_draft(draft: str, feedback: str) -> str:
    """Revise the draft based on feedback."""
    return f"Revised: {draft[:50]}... [Applied feedback: {feedback}]"


@workflow
async def review_pipeline(topic: str, ctx: RunContext) -> str:
    """Write a draft, get human review, then revise."""
    draft = await write_draft(topic)

    # ctx.request_info() suspends the workflow here. The caller gets back
    # a WorkflowRunResult with state IDLE_WITH_PENDING_REQUESTS and can
    # inspect the pending request via result.get_request_info_events().
    feedback = await ctx.request_info(
        {"draft": draft, "instructions": "Please review this draft"},
        response_type=str,
        request_id="review_request",
    )

    # This only executes after the caller resumes with run(responses={...}).
    # write_draft above returns its saved result (thanks to @step),
    # request_info returns the provided response, and we continue here.
    return await revise_draft(draft, feedback)


async def main():
    # Phase 1: Run until the workflow pauses for human input
    print("=== Phase 1: Initial run ===")
    result1 = await review_pipeline.run("AI Safety")

    # If request_info() was reached, the state is IDLE_WITH_PENDING_REQUESTS.
    # If the workflow completed without hitting request_info(), it would be IDLE.
    print(f"State: {result1.get_final_state()}")
    assert result1.get_final_state() == WorkflowRunState.IDLE_WITH_PENDING_REQUESTS

    requests = result1.get_request_info_events()
    print(f"Pending request: {requests[0].request_id}")

    # Phase 2: Resume with the human's response
    print("\n=== Phase 2: Resume with feedback ===")
    print("(write_draft should NOT execute again — saved by @step)")
    result2 = await review_pipeline.run(responses={"review_request": "Add more details about alignment research"})

    print(f"State: {result2.get_final_state()}")
    print(f"Output: {result2.get_outputs()[0]}")


if __name__ == "__main__":
    asyncio.run(main())
