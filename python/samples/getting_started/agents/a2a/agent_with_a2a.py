# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

import httpx
from a2a.client import A2ACardResolver
from agent_framework import A2AAgent


async def main():
    """Simple A2A agent usage - equivalent to .NET Program.cs"""

    # Get A2A agent host from environment
    a2a_agent_host = os.getenv("A2A_AGENT_HOST")
    if not a2a_agent_host:
        raise ValueError("A2A_AGENT_HOST environment variable is not set")

    print(f"Connecting to A2A agent at: {a2a_agent_host}")

    try:
        # Initialize A2ACardResolver with correct path for .NET server
        async with httpx.AsyncClient(timeout=60.0) as http_client:
            resolver = A2ACardResolver(httpx_client=http_client, base_url=a2a_agent_host)

            # Get agent card with the correct .NET server path
            agent_card = await resolver.get_agent_card(relative_card_path="/.well-known/agent.json")
            print(f"Found agent: {agent_card.name} - {agent_card.description}")

            # Create A2A agent instance
            agent = A2AAgent(
                name=agent_card.name, description=agent_card.description, agent_card=agent_card, url=a2a_agent_host
            )

            # Invoke the agent and output the result
            print("\nSending message to A2A agent...")
            response = await agent.run("Tell me a joke about a pirate.")

            # Print the response
            print("\nAgent Response:")
            for message in response.messages:
                print(message.text)

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
