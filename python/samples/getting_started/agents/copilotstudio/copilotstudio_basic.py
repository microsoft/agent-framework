# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework.microsoft import CopilotStudioAgent

"""
Copilot Studio Agent Basic Example

This sample demonstrates basic usage of CopilotStudioAgent with automatic configuration
from environment variables, showing both streaming and non-streaming responses.
"""

# Environment variables needed:
# COPILOTSTUDIOAGENT__ENVIRONMENTID - Environment ID where your copilot is deployed
# COPILOTSTUDIOAGENT__SCHEMANAME - Agent identifier/schema name of your copilot
# COPILOTSTUDIOAGENT__AGENTAPPID - Client ID for authentication
# COPILOTSTUDIOAGENT__TENANTID - Tenant ID for authentication


async def non_streaming_example() -> None:
    """Example of non-streaming response (get the complete result at once)."""
    print("=== Non-streaming Response Example ===")

    agent = CopilotStudioAgent()

    query = "What is the capital of France?"
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Agent: {result}\n")


async def streaming_example() -> None:
    """Example of streaming response (get results as they are generated)."""
    print("=== Streaming Response Example ===")

    agent = CopilotStudioAgent()

    query = "What is the capital of Spain?"
    print(f"User: {query}")
    print("Agent: ", end="", flush=True)
    async for chunk in agent.run_stream(query):
        if chunk.text:
            print(chunk.text, end="", flush=True)
    print("\n")


async def main() -> None:
    await non_streaming_example()
    await streaming_example()


if __name__ == "__main__":
    asyncio.run(main())
