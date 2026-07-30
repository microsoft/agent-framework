# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

import httpx
from a2a.client import A2ACardResolver
from agent_framework.a2a import A2AAgent
from dotenv import load_dotenv

load_dotenv()

"""
A2A Polling for Task Completion

This sample demonstrates how to poll a long-running A2A task for completion
using continuation tokens. When `background=True`, the agent returns immediately
with a continuation token that you can use to check progress later.

Key concepts demonstrated:
- Starting a background A2A task with `background=True`
- Receiving a continuation token for in-progress tasks
- Polling with `poll_task()` until the task reaches a terminal state

This is the A2A equivalent of the .NET A2AAgent_PollingForTaskCompletion sample.

Prerequisites:
- Set A2A_AGENT_HOST to the URL of a running A2A server

To run this sample:
    cd python/samples/02-agents/a2a
    uv run python a2a_polling.py
"""


async def main() -> None:
    """Demonstrates polling a long-running A2A task for completion."""
    a2a_agent_host = os.getenv("A2A_AGENT_HOST")
    if not a2a_agent_host:
        raise ValueError("A2A_AGENT_HOST environment variable is not set")

    # 1. Resolve agent card and create agent.
    async with httpx.AsyncClient(timeout=60.0) as http_client:
        resolver = A2ACardResolver(httpx_client=http_client, base_url=a2a_agent_host)
        agent_card = await resolver.get_agent_card()

    async with A2AAgent(
        name=agent_card.name,
        agent_card=agent_card,
        url=a2a_agent_host,
    ) as agent:
        # 2. Start a background task — the agent returns immediately.
        print("Starting background task...")
        response = await agent.run(
            "Write a detailed research report on quantum computing advances in 2025",
            background=True,
        )

        # 3. Check if we got a continuation token (task still in progress).
        if response.continuation_token is None:
            # Task completed immediately — no polling needed.
            print("Task completed immediately:")
            print(f"  {response.text}")
            return

        # 4. Poll until the task completes.
        token = response.continuation_token
        poll_count = 0
        while token is not None:
            poll_count += 1
            print(f"  Poll #{poll_count} — task still in progress, waiting 2s...")
            await asyncio.sleep(2)

            response = await agent.poll_task(token)  # type: ignore[arg-type]
            token = response.continuation_token

        # 5. Task is done — print the final response.
        print(f"\nTask completed after {poll_count} poll(s):")
        print(f"  {response.text[:200]}...")


if __name__ == "__main__":
    asyncio.run(main())


"""
Sample output:

Starting background task...
  Poll #1 — task still in progress, waiting 2s...
  Poll #2 — task still in progress, waiting 2s...
  Poll #3 — task still in progress, waiting 2s...

Task completed after 3 poll(s):
  Quantum computing has seen remarkable progress in 2025, with breakthroughs in...
"""
