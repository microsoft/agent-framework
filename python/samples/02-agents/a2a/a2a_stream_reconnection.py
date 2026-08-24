# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from typing import cast

import httpx
from a2a.client import A2ACardResolver
from agent_framework.a2a import A2AAgent
from agent_framework_a2a import A2AContinuationToken
from dotenv import load_dotenv

load_dotenv()

"""
A2A Stream Reconnection

This sample demonstrates how to reconnect to an interrupted A2A stream
using a continuation token. When streaming a long-running task, you can
capture the continuation token from any update and use it to resume the
stream later if the connection is lost.

Key concepts demonstrated:
- Streaming an A2A response with `stream=True`
- Capturing continuation tokens from in-progress updates
- Simulating a stream interruption (break)
- Resuming the stream with `run(continuation_token=..., stream=True)`

This is the A2A equivalent of the .NET A2AAgent_StreamReconnection sample.

Prerequisites:
- Set A2A_AGENT_HOST to the URL of a running A2A server

To run this sample:
    cd python/samples/02-agents/a2a
    uv run python a2a_stream_reconnection.py
"""


async def main() -> None:
    """Demonstrates reconnecting to an interrupted A2A stream."""
    a2a_agent_host = os.getenv("A2A_AGENT_HOST")
    if not a2a_agent_host:
        raise ValueError("A2A_AGENT_HOST environment variable is not set")

    # 1. Resolve agent card and create agent.
    async with httpx.AsyncClient(timeout=60.0) as http_client:
        resolver = A2ACardResolver(httpx_client=http_client, base_url=a2a_agent_host)
        agent_card = await resolver.get_agent_card()

    async with A2AAgent(
        name=agent_card.name,
        agent_card=agent_card,
        url=a2a_agent_host,
    ) as agent:
        # 2. Start a streaming background task.
        print("Starting streaming task...")
        stream = agent.run(
            "Write a long essay about the history of artificial intelligence",
            stream=True,
            background=True,
        )

        # 3. Read a few updates, capture the continuation token, then "disconnect".
        saved_token = None
        update_count = 0
        async for update in stream:
            update_count += 1
            if update.continuation_token:
                saved_token = update.continuation_token
            for content in update.contents:
                if content.text:
                    print(content.text, end="", flush=True)

            # Simulate a disconnect after receiving 3 updates.
            if update_count >= 3:
                print("\n\n--- Connection interrupted! ---\n")
                break

        if saved_token is None:
            print("No continuation token received — task may have completed before interruption.")
            return

        # 4. Reconnect using the saved continuation token.
        #    background=True is required so that in-progress task updates
        #    surface continuation tokens (matching the A2AAgent contract).
        print("Reconnecting with continuation token...")
        resumed_stream = agent.run(
            continuation_token=cast(A2AContinuationToken, saved_token),
            stream=True,
            background=True,
        )

        # 5. Continue receiving updates from where we left off.
        async for update in resumed_stream:
            update_count += 1
            for content in update.contents:
                if content.text:
                    print(content.text, end="", flush=True)
        print()  # newline after streaming completes

        response = await resumed_stream.get_final_response()
        print(f"\nStream completed. Total updates: {update_count}")
        print(f"Final response: {len(response.messages)} message(s)")


if __name__ == "__main__":
    asyncio.run(main())


"""
Sample output:

Starting streaming task...
Policy:

--- Connection interrupted! ---

Reconnecting with continuation token (task_id=task-abc123)...
 Short Shipment Dispute Handling Policy V2.1

Summary: "For short shipments reported by customers, first verify internal..."

Stream completed. Total updates: 106
Final response: 103 message(s)
"""
