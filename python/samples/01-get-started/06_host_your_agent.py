# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

import httpx
from a2a.client import A2ACardResolver
from agent_framework.a2a import A2AAgent

"""
Step 6: Host Your Agent with A2A

Expose your agent over the Agent-to-Agent (A2A) protocol so other agents
(or any HTTP client) can discover and call it.

Prerequisites:
  - Set A2A_AGENT_HOST to point at a running A2A-compliant agent endpoint.
  - The target agent must expose its AgentCard at /.well-known/agent.json

For more on hosting, see: ../04-hosting/
For docs: https://learn.microsoft.com/agent-framework/get-started/host-your-agent
For A2A spec: https://a2a-protocol.org/latest/
"""


async def main():
    # <connect_to_agent>
    a2a_agent_host = os.getenv("A2A_AGENT_HOST")
    if not a2a_agent_host:
        raise ValueError("Set the A2A_AGENT_HOST environment variable (e.g. https://my-agent.example.com)")

    print(f"Connecting to A2A agent at: {a2a_agent_host}")

    async with httpx.AsyncClient(timeout=60.0) as http_client:
        resolver = A2ACardResolver(httpx_client=http_client, base_url=a2a_agent_host)
        agent_card = await resolver.get_agent_card()
        print(f"Found agent: {agent_card.name} — {agent_card.description}")

        agent = A2AAgent(
            name=agent_card.name,
            description=agent_card.description,
            agent_card=agent_card,
            url=a2a_agent_host,
        )
    # </connect_to_agent>

    # <invoke_agent>
    print("\nSending message to A2A agent...")
    response = await agent.run("What are your capabilities?")

    print("\nAgent Response:")
    for message in response.messages:
        print(message.text)
    # </invoke_agent>


if __name__ == "__main__":
    asyncio.run(main())
