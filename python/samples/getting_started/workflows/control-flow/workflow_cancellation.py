# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import WorkflowBuilder, WorkflowContext, executor
from typing_extensions import Never

"""
Sample: Workflow Cancellation

A three-step workflow where each step takes 2 seconds. We cancel it after 3 seconds
to demonstrate mid-execution cancellation using asyncio tasks.

Purpose:
Show how to cancel a running workflow by wrapping it in an asyncio.Task. This pattern
works with both workflow.run() and workflow.run_stream(). Useful for implementing
timeouts, graceful shutdown, or A2A executors that need cancellation support.

Prerequisites:
- No external services required.
"""


@executor(id="step1")
async def step1(text: str, ctx: WorkflowContext[str]) -> None:
    """First step - simulates 2 seconds of work."""
    print("[Step1] Starting...")
    await asyncio.sleep(2)
    print("[Step1] Done")
    await ctx.send_message(text.upper())


@executor(id="step2")
async def step2(text: str, ctx: WorkflowContext[str]) -> None:
    """Second step - simulates 2 seconds of work."""
    print("[Step2] Starting...")
    await asyncio.sleep(2)
    print("[Step2] Done")
    await ctx.send_message(text + "!")


@executor(id="step3")
async def step3(text: str, ctx: WorkflowContext[Never, str]) -> None:
    """Final step - simulates 2 seconds of work."""
    print("[Step3] Starting...")
    await asyncio.sleep(2)
    print("[Step3] Done")
    await ctx.yield_output(f"Result: {text}")


def build_workflow():
    """Build a simple 3-step sequential workflow (~6 seconds total)."""
    return (
        WorkflowBuilder()
        .register_executor(lambda: step1, name="step1")
        .register_executor(lambda: step2, name="step2")
        .register_executor(lambda: step3, name="step3")
        .add_edge("step1", "step2")
        .add_edge("step2", "step3")
        .set_start_executor("step1")
        .build()
    )


async def run_with_cancellation() -> None:
    """Cancel the workflow after 3 seconds (mid-execution during Step2)."""
    print("=== Run with cancellation ===\n")
    workflow = build_workflow()

    # Wrap workflow.run() in a task to enable cancellation
    task = asyncio.create_task(workflow.run("hello world"))

    # Wait 3 seconds (Step1 completes, Step2 is mid-execution), then cancel
    await asyncio.sleep(3)
    print("\n--- Cancelling workflow ---\n")
    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        print("Workflow was cancelled")


async def run_to_completion() -> None:
    """Let the workflow run to completion and get the result."""
    print("=== Run to completion ===\n")
    workflow = build_workflow()

    # Run without cancellation - await the result directly
    result = await workflow.run("hello world")

    print(f"\nWorkflow completed with output: {result.get_outputs()}")


async def main() -> None:
    """Demonstrate both cancellation and completion scenarios."""
    await run_with_cancellation()
    print("\n")
    await run_to_completion()


if __name__ == "__main__":
    asyncio.run(main())
