# Copyright (c) Microsoft. All rights reserved.

"""A2A client script for the local_a2a sample.

Connects to a running ``local_a2a`` server using the A2A protocol, discovers the
hosted agent's capabilities, and sends a weather question.

Usage::

    # 1. Start the server in another terminal:
    uv run python app.py

    # 2. Run this client:
    uv run python call_client.py
"""

from __future__ import annotations

import asyncio

from agent_framework_a2a import A2AAgent


async def main() -> None:
    """Discover and call the hosted A2A agent."""
    base_url = "http://127.0.0.1:8000"

    async with A2AAgent(url=base_url) as agent:
        print(f"Connected to A2A agent at {base_url}")

        # Non-streaming request
        print("\n--- Non-streaming ---")
        response = await agent.run("What is the weather in Seattle?")
        print(response.text)

        # Streaming request — print chunks as they arrive
        print("\n--- Streaming ---")
        stream = agent.run("What is the weather in Tokyo?", stream=True)
        async for update in stream:
            for content in update.contents:
                if content.text:
                    print(content.text, end="", flush=True)
        print()
        final = await stream.get_final_response()
        print(f"\nFinal response: {final.text}")


if __name__ == "__main__":
    asyncio.run(main())
