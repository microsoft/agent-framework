# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

import httpx
from a2a.client import A2ACardResolver
from agent_framework.a2a import A2AAgent
from dotenv import load_dotenv

load_dotenv()

"""
A2A Protocol Selection

This sample demonstrates how to configure which protocol binding the A2A client
uses when connecting to a remote agent. The A2A specification defines three
standard bindings: JSONRPC, GRPC, and HTTP+JSON. Agents declare their supported
bindings in their AgentCard, and clients can express a preference.

Key concepts demonstrated:
- Configuring `supported_protocol_bindings` on A2AAgent
- The client selects a binding that matches the remote agent's capabilities
- Fallback behavior when preferred binding is unavailable

This is the A2A equivalent of the .NET A2AAgent_ProtocolSelection sample.

Prerequisites:
- Set A2A_AGENT_HOST to the URL of a running A2A server

To run this sample:
    cd python/samples/02-agents/a2a
    uv run python a2a_protocol_selection.py
"""


async def main() -> None:
    """Demonstrates configuring A2A protocol binding preferences."""
    a2a_agent_host = os.getenv("A2A_AGENT_HOST")
    if not a2a_agent_host:
        raise ValueError("A2A_AGENT_HOST environment variable is not set")

    # 1. Resolve agent card to see what bindings are available.
    async with httpx.AsyncClient(timeout=60.0) as http_client:
        resolver = A2ACardResolver(httpx_client=http_client, base_url=a2a_agent_host)
        agent_card = await resolver.get_agent_card()

    print(f"Agent: {agent_card.name}")
    print("Supported interfaces:")
    for interface in agent_card.supported_interfaces:
        print(f"  - {interface.protocol_binding} @ {interface.url}")

    # 2. Create agent with explicit protocol binding preference.
    #    The list is ordered by preference — the SDK will select the first
    #    binding that matches a supported interface on the agent card.
    #
    #    This matters when a server exposes multiple interfaces (e.g. JSONRPC
    #    on / and HTTP+JSON on /api/). If only one binding is available, the
    #    client uses it regardless of your preference list.
    async with A2AAgent(
        name=agent_card.name,
        agent_card=agent_card,
        url=a2a_agent_host,
        supported_protocol_bindings=["HTTP+JSON", "JSONRPC"],
    ) as agent:
        print("\nConfigured bindings: ['HTTP+JSON', 'JSONRPC']")
        response = await agent.run("Tell me a short joke")
        print(f"Response: {response.text}")


if __name__ == "__main__":
    asyncio.run(main())


"""
Sample output:

Agent: PolicyAgent
Supported interfaces:
  - JSONRPC @ http://localhost:5001/

Configured bindings: ['HTTP+JSON', 'JSONRPC']
Response: Here's a short joke for you...
"""
