# Copyright (c) Microsoft. All rights reserved.

"""Parallel pipeline using asyncio.gather with functional workflows.

Fan-out/fan-in uses native Python concurrency via asyncio.gather.
No @step needed — still just plain async functions.
"""

import asyncio

from agent_framework import workflow


# Plain async functions — asyncio.gather handles the concurrency,
# no framework primitives needed for parallelism.
async def research_web(topic: str) -> str:
    """Simulate web research."""
    await asyncio.sleep(0.05)
    return f"Web results for '{topic}': 10 articles found"


async def research_papers(topic: str) -> str:
    """Simulate academic paper search."""
    await asyncio.sleep(0.05)
    return f"Papers on '{topic}': 3 relevant papers"


async def research_news(topic: str) -> str:
    """Simulate news search."""
    await asyncio.sleep(0.05)
    return f"News about '{topic}': 5 recent articles"


async def synthesize(sources: list[str]) -> str:
    """Combine research results into a summary."""
    return "Research Summary:\n" + "\n".join(f"  - {s}" for s in sources)


# @workflow wraps the orchestration logic so you get .run(), streaming,
# and events. The functions it calls are plain Python — no decorators
# needed just because they're inside a workflow.
@workflow
async def research_pipeline(topic: str) -> str:
    """Fan-out to three research tasks, then synthesize results."""
    # asyncio.gather runs all three concurrently — this is standard Python,
    # not a framework concept. Use it the same way you would anywhere else.
    #
    # Tip: if any of these were wrapped with @step (e.g. an expensive agent call),
    # the pattern is identical — @step composes with asyncio.gather, so each
    # branch is independently cached on HITL resume or checkpoint restore.
    web, papers, news = await asyncio.gather(
        research_web(topic),
        research_papers(topic),
        research_news(topic),
    )

    return await synthesize([web, papers, news])


async def main():
    result = await research_pipeline.run("AI agents")
    print(result.get_outputs()[0])


if __name__ == "__main__":
    asyncio.run(main())
