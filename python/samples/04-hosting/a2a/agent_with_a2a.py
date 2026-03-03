# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

import httpx
from a2a.client import A2ACardResolver
from agent_framework.a2a import A2AAgent
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
Agent2Agent (A2A) Protocol Integration Sample

This sample demonstrates how to connect to and communicate with external agents using
the A2A protocol. A2A is a standardized communication protocol that enables interoperability
between different agent systems, allowing agents built with different frameworks and
technologies to communicate seamlessly.

By default the A2AAgent waits for the remote agent to finish before returning (background=False).
This means long-running A2A tasks are handled transparently — the caller simply awaits the result.
For advanced scenarios where you need to poll or resubscribe to in-progress tasks, see the
background_responses sample: samples/concepts/background_responses.py

For more information about the A2A protocol specification, visit: https://a2a-protocol.org/latest/

Key concepts demonstrated:
- Discovering A2A-compliant agents using AgentCard resolution
- Creating A2AAgent instances to wrap external A2A endpoints
- Non-streaming request/response
- Streaming responses to receive incremental updates via SSE

To run this sample:
1. Set the A2A_AGENT_HOST environment variable to point to an A2A-compliant agent endpoint
   Example: export A2A_AGENT_HOST="https://your-a2a-agent.example.com"
2. Ensure the target agent exposes its AgentCard at /.well-known/agent.json
3. Run: uv run python agent_with_a2a.py

Visit the README.md for more details on setting up and running A2A agents.
"""


async def main():
    """Demonstrates connecting to and communicating with an A2A-compliant agent."""
    # 1. Get A2A agent host from environment.
    a2a_agent_host = os.getenv("A2A_AGENT_HOST")
    if not a2a_agent_host:
        raise ValueError("A2A_AGENT_HOST environment variable is not set")

    print(f"Connecting to A2A agent at: {a2a_agent_host}")

    # 2. Resolve the agent card to discover capabilities.
    async with httpx.AsyncClient(timeout=60.0) as http_client:
        resolver = A2ACardResolver(httpx_client=http_client, base_url=a2a_agent_host)
        agent_card = await resolver.get_agent_card()
        print(f"Found agent: {agent_card.name} - {agent_card.description}")

    # 3. Create A2A agent instance.
    async with A2AAgent(
        name=agent_card.name,
        description=agent_card.description,
        agent_card=agent_card,
        url=a2a_agent_host,
    ) as agent:
        # 4. Simple request/response — the agent waits for completion internally.
        #    Even if the remote agent takes a while, background=False (the default)
        #    means the call blocks until a terminal state is reached.
        print("\n--- Non-streaming response ---")
        response = await agent.run("What are your capabilities?")

        print("Agent Response:")
        for message in response.messages:
            print(f"  {message.text}")

        # 5. Stream a response — the natural model for A2A.
        #    Updates arrive as Server-Sent Events, letting you observe
        #    progress in real time as the remote agent works.
        print("\n--- Streaming response ---")
        async with agent.run("Tell me about yourself", stream=True) as stream:
            async for update in stream:
                for content in update.contents:
                    if content.text:
                        print(f"  {content.text}")

            response = await stream.get_final_response()
            print(f"\nFinal response ({len(response.messages)} message(s)):")
            for message in response.messages:
                print(f"  {message.text}")


if __name__ == "__main__":
    asyncio.run(main())


"""
Sample output:

Connecting to A2A agent at: http://localhost:5001/
Found agent: MyAgent - A helpful AI assistant

--- Non-streaming response ---
Agent Response:
  I can help with code generation, analysis, and general Q&A.

--- Streaming response ---
  I am an AI assistant built to help with various tasks.

Final response (1 message(s)):
  I am an AI assistant built to help with various tasks.
"""
