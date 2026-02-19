# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "semantic-kernel",
# ]
# ///
# Run with any PEP 723 compatible runner, e.g.:
#   uv run samples/semantic-kernel-migration/copilot_studio/01_basic_copilot_studio_agent.py

# Copyright (c) Microsoft. All rights reserved.
"""Call a Copilot Studio agent with SK and Agent Framework."""

import asyncio

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


async def run_semantic_kernel() -> None:
    from semantic_kernel.agents import CopilotStudioAgent

    # SK agent talks to the configured Copilot Studio bot directly.
    agent = CopilotStudioAgent(
        name="PhysicsAgent",
        instructions="Answer physics questions concisely.",
    )
    response = await agent.get_response("Why is the sky blue?")
    print("[SK]", response.message.content)


async def run_agent_framework() -> None:
    from agent_framework.microsoft import CopilotStudioAgent

    # AF exposes an equivalent CopilotStudioAgent wrapper.
    agent = CopilotStudioAgent(
        name="PhysicsAgent",
        instructions="Answer physics questions concisely.",
    )
    reply = await agent.run("Why is the sky blue?")
    print("[AF]", reply.text)


async def main() -> None:
    await run_semantic_kernel()
    await run_agent_framework()


if __name__ == "__main__":
    asyncio.run(main())
