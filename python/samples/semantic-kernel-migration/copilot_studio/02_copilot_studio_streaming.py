# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "semantic-kernel",
# ]
# ///
# Run with any PEP 723 compatible runner, e.g.:
#   uv run samples/semantic-kernel-migration/copilot_studio/02_copilot_studio_streaming.py

# Copyright (c) Microsoft. All rights reserved.
"""Stream responses from Copilot Studio agents in SK and AF."""

import asyncio

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


async def run_semantic_kernel() -> None:
    from semantic_kernel.agents import CopilotStudioAgent

    agent = CopilotStudioAgent(
        name="TourGuide",
        instructions="Provide travel recommendations in short bursts.",
    )
    # SK streaming yields chunks with message metadata.
    print("[SK][stream]", end=" ")
    async for chunk in agent.invoke_stream("Plan a day in Copenhagen for foodies."):
        if chunk.message:
            print(chunk.message.content, end="", flush=True)
    print()


async def run_agent_framework() -> None:
    from agent_framework.microsoft import CopilotStudioAgent

    agent = CopilotStudioAgent(
        name="TourGuide",
        instructions="Provide travel recommendations in short bursts.",
    )
    # AF streaming provides incremental AgentResponseUpdate objects.
    print("[AF][stream]", end=" ")
    async for update in agent.run("Plan a day in Copenhagen for foodies.", stream=True):
        if update.text:
            print(update.text, end="", flush=True)
    print()


async def main() -> None:
    await run_semantic_kernel()
    await run_agent_framework()


if __name__ == "__main__":
    asyncio.run(main())
