# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

import httpx
from a2a.client import A2ACardResolver
from agent_framework.a2a import A2AAgent

"""
Agent2Agent (A2A) Protocol Integration Sample

This sample demonstrates how to connect to and communicate with external agents using
the A2A protocol. A2A is a standardized communication protocol that enables interoperability
between different agent systems, allowing agents built with different frameworks and
technologies to communicate seamlessly.

For more information about the A2A protocol specification, visit: https://a2a-protocol.org/latest/

Key concepts demonstrated:
- Discovering A2A-compliant agents using AgentCard resolution
- Creating A2AAgent instances to wrap external A2A endpoints
- Converting Agent Framework messages to A2A protocol format
- Handling A2A responses (Messages and Tasks) back to framework types

To run this sample:
1. Set the A2A_AGENT_HOST environment variable to point to an A2A-compliant agent endpoint
   Example: export A2A_AGENT_HOST="https://your-a2a-agent.example.com"
2. Ensure the target agent exposes its AgentCard at /.well-known/agent.json
3. Run: uv run python agent_with_a2a.py

The sample will:
- Connect to the specified A2A agent endpoint
- Retrieve and parse the agent's capabilities via its AgentCard
- Send a message using the A2A protocol
- Display the agent's response

Visit the README.md for more details on setting up and running A2A agents.
"""


async def main():
    """Demonstrates connecting to and communicating with an A2A-compliant agent."""
    # Get A2A agent host from environment
    a2a_agent_host = os.getenv("A2A_AGENT_HOST")
    if not a2a_agent_host:
        raise ValueError("A2A_AGENT_HOST environment variable is not set")

    print(f"Connecting to A2A agent at: {a2a_agent_host}")

    # Initialize A2ACardResolver
    async with httpx.AsyncClient(timeout=60.0) as http_client:
        resolver = A2ACardResolver(httpx_client=http_client, base_url=a2a_agent_host)

        # Get agent card
        agent_card = await resolver.get_agent_card()
        print(f"Found agent: {agent_card.name} - {agent_card.description}")

        # Create A2A agent instance
        agent = A2AAgent(
            name=agent_card.name,
            description=agent_card.description,
            agent_card=agent_card,
            url=a2a_agent_host,
        )

        # Invoke the agent and output the result
        print("\nSending message to A2A agent...")
        response = await agent.run("What are your capabilities?")

        # Print the response
        print("\nAgent Response:")
        for message in response.messages:
            print(message.text)


if __name__ == "__main__":
    asyncio.run(main())
