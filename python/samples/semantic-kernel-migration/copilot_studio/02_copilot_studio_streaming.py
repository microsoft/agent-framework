# Copyright (c) Microsoft. All rights reserved.
"""Stream responses from Copilot Studio agents in SK and AF."""

import asyncio


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
    async for update in agent.run_stream("Plan a day in Copenhagen for foodies."):
        if update.text:
            print(update.text, end="", flush=True)
    print()


async def main() -> None:
    await run_semantic_kernel()
    await run_agent_framework()


if __name__ == "__main__":
    asyncio.run(main())
