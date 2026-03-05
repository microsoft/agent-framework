# Copyright (c) Microsoft. All rights reserved.

"""Basic streaming pipeline using the functional workflow API.

Stream workflow events in real time with run(stream=True).
"""

import asyncio

from agent_framework import workflow


# Plain async functions — no decorators needed for simple helpers.
async def fetch_data(url: str) -> dict[str, str | int]:
    """Simulate fetching data from a URL."""
    return {"url": url, "content": f"Data from {url}", "status": 200}


async def transform_data(data: dict[str, str | int]) -> str:
    """Transform raw data into a summary string."""
    return f"[{data['status']}] {data['content']}"


async def validate_result(summary: str) -> bool:
    """Validate the transformed result."""
    return len(summary) > 0 and "[200]" in summary


# @workflow enables .run(stream=True), which returns a ResponseStream
# you can iterate over with `async for`. Without @workflow, you'd just
# have a normal async function with no streaming capability.
@workflow
async def data_pipeline(url: str) -> str:
    """A simple sequential data pipeline."""
    raw = await fetch_data(url)
    summary = await transform_data(raw)
    is_valid = await validate_result(summary)

    return f"{summary} (valid={is_valid})"


async def main():
    # run(stream=True) returns a ResponseStream that yields events as they
    # are produced. The raw stream includes lifecycle events (started, status)
    # alongside application events — filter by event.type to find what you need.
    stream = data_pipeline.run("https://example.com/api/data", stream=True)
    async for event in stream:
        if event.type == "output":
            print(f"Output: {event.data}")

    # After iteration, get_final_response() returns the WorkflowRunResult
    result = await stream.get_final_response()
    print(f"Final state: {result.get_final_state()}")


if __name__ == "__main__":
    asyncio.run(main())
