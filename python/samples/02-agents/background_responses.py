# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import Agent
from agent_framework.openai import OpenAIResponsesClient
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""Background Responses Sample.

This sample demonstrates long-running agent operations using the OpenAI
Responses API ``background`` option.  Two patterns are shown:

1. **Non-streaming polling** – start a background run, then poll with the
   ``continuation_token`` until the operation completes.
2. **Streaming with resumption** – start a background streaming run, simulate
   an interruption, and resume from the last ``continuation_token``.

Prerequisites:
  - Set the ``OPENAI_API_KEY`` environment variable.
  - A model that benefits from background execution (e.g. ``o3``).
"""


# 1. Create the agent with an OpenAI Responses client.
agent = Agent(
    name="researcher",
    instructions="You are a helpful research assistant. Be concise.",
    client=OpenAIResponsesClient(model_id="o3"),
)


async def non_streaming_polling() -> None:
    """Demonstrate non-streaming background run with polling."""
    print("=== Non-Streaming Polling ===\n")

    session = agent.create_session()

    # 2. Start a background run — returns immediately.
    response = await agent.run(
        messages="Briefly explain the theory of relativity in two sentences.",
        session=session,
        options={"background": True},
    )

    print(f"Initial status: continuation_token={'set' if response.continuation_token else 'None'}")

    # 3. Poll until the operation completes.
    poll_count = 0
    while response.continuation_token is not None:
        poll_count += 1
        await asyncio.sleep(2)
        response = await agent.run(
            session=session,
            options={"continuation_token": response.continuation_token},
        )
        print(f"  Poll {poll_count}: continuation_token={'set' if response.continuation_token else 'None'}")

    # 4. Done — print the final result.
    print(f"\nResult ({poll_count} poll(s)):\n{response.text}\n")


async def streaming_with_resumption() -> None:
    """Demonstrate streaming background run with simulated interruption and resumption."""
    print("=== Streaming with Resumption ===\n")

    session = agent.create_session()

    # 2. Start a streaming background run.
    last_token = None
    stream = agent.run(
        messages="Briefly list three benefits of exercise.",
        stream=True,
        session=session,
        options={"background": True},
    )

    # 3. Read some chunks, then simulate an interruption.
    chunk_count = 0
    print("First stream (before interruption):")
    async for update in stream:
        last_token = update.continuation_token
        if update.text:
            print(update.text, end="", flush=True)
        chunk_count += 1
        if chunk_count >= 3:
            print("\n  [simulated interruption]")
            break

    # 4. Resume from the last continuation token.
    if last_token is not None:
        print("Resumed stream:")
        stream = agent.run(
            stream=True,
            session=session,
            options={"continuation_token": last_token},
        )
        async for update in stream:
            if update.text:
                print(update.text, end="", flush=True)

    print("\n")


async def main() -> None:
    await non_streaming_polling()
    await streaming_with_resumption()


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:

=== Non-Streaming Polling ===

Initial status: continuation_token=set
  Poll 1: continuation_token=set
  Poll 2: continuation_token=None

Result (2 poll(s)):
The theory of relativity, developed by Albert Einstein, consists of special
relativity (1905), which shows that the laws of physics are the same for all
non-accelerating observers and that the speed of light is constant, and general
relativity (1915), which describes gravity as the curvature of spacetime caused
by mass and energy.

=== Streaming with Resumption ===

First stream (before interruption):
Here are three
  [simulated interruption]
Resumed stream:
key benefits of regular exercise:

1. **Improved cardiovascular health** ...
2. **Better mental health** ...
3. **Stronger muscles and bones** ...
"""
