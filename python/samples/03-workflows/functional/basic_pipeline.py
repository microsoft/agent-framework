# Copyright (c) Microsoft. All rights reserved.

"""Basic sequential pipeline using the functional workflow API.

The simplest possible workflow: plain async functions orchestrated by @workflow.
No @step decorator needed — just write Python.
"""

import asyncio

from agent_framework import workflow


# These are plain async functions — no decorators needed.
# They run normally inside the workflow, just like any other Python function.
async def fetch_data(url: str) -> dict[str, str | int]:
    """Simulate fetching data from a URL."""
    return {"url": url, "content": f"Data from {url}", "status": 200}


async def transform_data(data: dict[str, str | int]) -> str:
    """Transform raw data into a summary string."""
    return f"[{data['status']}] {data['content']}"


# @workflow turns this async function into a FunctionalWorkflow object.
# Without it, this is just a normal async function. With it, you get:
#   - .run() that returns a WorkflowRunResult with events and outputs
#   - .run(stream=True) for streaming events in real time
#   - .as_agent() to use this workflow anywhere an agent is expected
#
# The function's first parameter receives the input from .run("...").
# Add a `ctx: RunContext` parameter only if you need HITL, state, or custom events.
@workflow
async def data_pipeline(url: str) -> str:
    """A simple sequential data pipeline."""
    raw = await fetch_data(url)
    summary = await transform_data(raw)

    # This is just a function — plain Python works between calls.
    # No need to wrap every operation in a separate async function.
    is_valid = len(summary) > 0 and "[200]" in summary
    tag = "VALID" if is_valid else "INVALID"

    # Returning a value automatically emits it as an output.
    # Callers retrieve it via result.get_outputs().
    return f"[{tag}] {summary}"


async def main():
    # .run() is provided by @workflow — a plain async function wouldn't have it
    result = await data_pipeline.run("https://example.com/api/data")
    print("Output:", result.get_outputs()[0])
    print("State:", result.get_final_state())


if __name__ == "__main__":
    asyncio.run(main())
