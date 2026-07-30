# Copyright (c) Microsoft. All rights reserved.

"""Introducing @step: per-step checkpointing and observability.

The previous samples used plain functions — and that works. Workflows support
HITL (ctx.request_info) and checkpointing regardless of whether you use @step.

The difference: without @step, a resumed workflow re-executes every function
call from the top. That's fine for cheap functions. But for expensive operations
(API calls, agent runs, etc.) you don't want to pay that cost again.

@step saves each function's result so it skips re-execution on resume:
- On HITL resume, completed steps return their saved result instantly.
- On crash recovery from a checkpoint, earlier step results are restored.
- Each step emits executor_invoked/executor_completed events for observability.

@step is opt-in. Plain functions still work alongside @step in the same workflow.
"""

import asyncio

from agent_framework import InMemoryCheckpointStorage, step, workflow

# Track call counts to show which functions actually execute on resume
fetch_calls = 0
transform_calls = 0


# @step saves this function's result. On resume, it returns the saved
# result instead of re-executing — useful because this is expensive.
@step
async def fetch_data(url: str) -> dict[str, str | int]:
    """Expensive operation — @step prevents re-execution on resume."""
    global fetch_calls
    fetch_calls += 1
    print(f"  fetch_data called (call #{fetch_calls})")
    return {"url": url, "content": f"Data from {url}", "status": 200}


@step
async def transform_data(data: dict[str, str | int]) -> str:
    """Another expensive operation — @step saves the result."""
    global transform_calls
    transform_calls += 1
    print(f"  transform_data called (call #{transform_calls})")
    return f"[{data['status']}] {data['content']}"


# No @step — this is cheap, so it just re-runs on resume. That's fine.
async def validate_result(summary: str) -> bool:
    """Cheap validation — no @step needed."""
    return len(summary) > 0 and "[200]" in summary


storage = InMemoryCheckpointStorage()


# checkpoint_storage tells @workflow where to persist step results.
# Each @step saves a checkpoint after it completes.
@workflow(checkpoint_storage=storage)
async def data_pipeline(url: str) -> str:
    """Mix of @step functions and plain functions."""
    raw = await fetch_data(url)
    summary = await transform_data(raw)
    is_valid = await validate_result(summary)

    return f"{summary} (valid={is_valid})"


async def main():
    # --- Run 1: Everything executes normally ---
    print("=== Run 1: Fresh execution ===")
    result = await data_pipeline.run("https://example.com/api/data")
    print(f"Output: {result.get_outputs()[0]}")
    print(f"fetch_calls={fetch_calls}, transform_calls={transform_calls}")

    # @step functions emit executor events; plain functions don't.
    print("\nEvents:")
    for event in result:
        if event.type in ("executor_invoked", "executor_completed"):
            print(f"  {event.type}: {event.executor_id}")

    # --- Run 2: Restore from checkpoint ---
    # The workflow re-executes, but @step functions return saved results.
    # Only validate_result() (no @step) actually runs again.
    print("\n=== Run 2: Restored from checkpoint ===")
    latest = await storage.get_latest(workflow_name="data_pipeline")
    assert latest is not None

    result2 = await data_pipeline.run(checkpoint_id=latest.checkpoint_id)
    print(f"Output: {result2.get_outputs()[0]}")
    print(f"fetch_calls={fetch_calls}, transform_calls={transform_calls}")
    print("(call counts unchanged — @step results were restored from checkpoint)")


if __name__ == "__main__":
    asyncio.run(main())
