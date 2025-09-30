# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework.microsoft import CopilotStudioAgent

"""
Copilot Studio Agent Basic Example

This sample demonstrates the fundamental usage of Microsoft Copilot Studio agents
with the Agent Framework. The example includes:

- Creating agents using CopilotStudioAgent with automatic configuration from environment variables
- Non-streaming response example to get complete results at once
- Streaming response example to receive results as they are generated
- Simple question-answering interactions with published Copilot Studio agents
- Automatic authentication handling with MSAL (Microsoft Authentication Library)
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
