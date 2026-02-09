# Copyright (c) Microsoft. All rights reserved.

"""
A2A (Agent-to-Agent) Protocol Sample

Demonstrates connecting to and communicating with external agents using the
A2A protocol — a standardized communication protocol for agent interoperability.

What you'll learn:
- Discovering A2A-compliant agents using AgentCard resolution
- Creating A2AAgent instances to wrap external A2A endpoints
- Sending messages and handling responses via A2A protocol

Prerequisites:
- Set A2A_AGENT_HOST environment variable to an A2A-compliant agent endpoint
- The target agent must expose its AgentCard at /.well-known/agent.json

For more about A2A: https://a2a-protocol.org/latest/
Docs: https://learn.microsoft.com/agent-framework/integrations/overview
"""

import asyncio
import os

import httpx
from a2a.client import A2ACardResolver
from agent_framework.a2a import A2AAgent


# <running>
async def main():
    """Demonstrates connecting to and communicating with an A2A-compliant agent."""
    a2a_agent_host = os.getenv("A2A_AGENT_HOST")
    if not a2a_agent_host:
        raise ValueError("A2A_AGENT_HOST environment variable is not set")

    print(f"Connecting to A2A agent at: {a2a_agent_host}")

    async with httpx.AsyncClient(timeout=60.0) as http_client:
        resolver = A2ACardResolver(httpx_client=http_client, base_url=a2a_agent_host)

        # <agent_discovery>
        agent_card = await resolver.get_agent_card()
        print(f"Found agent: {agent_card.name} - {agent_card.description}")

        agent = A2AAgent(
            name=agent_card.name,
            description=agent_card.description,
            agent_card=agent_card,
            url=a2a_agent_host,
        )
        # </agent_discovery>

        print("\nSending message to A2A agent...")
        response = await agent.run("What are your capabilities?")

        print("\nAgent Response:")
        for message in response.messages:
            print(message.text)
# </running>


if __name__ == "__main__":
    asyncio.run(main())
