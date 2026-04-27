# Copyright (c) Microsoft. All rights reserved.

"""
Doubleword Chat Client Example

This sample demonstrates how to use the Microsoft Agent Framework with
Doubleword's OpenAI-compatible inference API. Doubleword is an AI model
gateway providing unified routing, management, and security for inference
across multiple model providers.

Since Doubleword exposes an OpenAI-compatible API, you can use the built-in
OpenAIChatCompletionClient with a custom base URL.

Three execution modes are demonstrated:
- main()       — realtime (priority tier)
- main_async() — 1-hour async (flex tier, mid-tier cost)
- main_batch() — 24-hour batch (deepest discount)

Setup:
    pip install agent-framework-openai
    export DOUBLEWORD_API_KEY="your-api-key"

Available models: https://docs.doubleword.ai/inference-api/models
"""

import asyncio
import os

from agent_framework import Message
from agent_framework.openai import OpenAIChatCompletionClient


async def main() -> None:
    """Run a basic prompt using Doubleword's inference API."""
    client = OpenAIChatCompletionClient(
        model="Qwen/Qwen3.5-397B-A17B-FP8",
        base_url="https://api.doubleword.ai/v1",
        api_key=os.environ["DOUBLEWORD_API_KEY"],
    )

    message = Message("user", contents=["Explain the benefits of an AI model gateway in one paragraph."])
    print(f"User: {message.text}")

    response = await client.get_response([message], stream=False)
    print(f"Assistant: {response}")


async def main_async() -> None:
    """Run requests on the 1-hour async (flex) tier using autobatcher.

    Mid-tier cost between realtime and 24-hour batch — use when next-day
    batch turnaround is too slow but realtime is too expensive.

    Install: pip install autobatcher
    See: https://pypi.org/project/autobatcher/
    """
    from autobatcher import AsyncOpenAI

    client = OpenAIChatCompletionClient(
        model="Qwen/Qwen3.5-397B-A17B-FP8",
        async_client=AsyncOpenAI(
            api_key=os.environ["DOUBLEWORD_API_KEY"],
            base_url="https://api.doubleword.ai/v1",
        ),
    )

    message = Message("user", contents=["Explain the benefits of an AI model gateway in one paragraph."])
    print(f"User: {message.text}")

    response = await client.get_response([message], stream=False)
    print(f"Assistant: {response}")


async def main_batch() -> None:
    """Run batch requests at reduced cost using autobatcher.

    24-hour batch tier — deepest discount (up to ~90% off realtime).

    Install: pip install autobatcher
    See: https://pypi.org/project/autobatcher/
    """
    from autobatcher import BatchOpenAI

    client = OpenAIChatCompletionClient(
        model="Qwen/Qwen3.5-397B-A17B-FP8",
        async_client=BatchOpenAI(
            api_key=os.environ["DOUBLEWORD_API_KEY"],
            base_url="https://api.doubleword.ai/v1",
        ),
    )

    message = Message("user", contents=["Explain the benefits of an AI model gateway in one paragraph."])
    print(f"User: {message.text}")

    response = await client.get_response([message], stream=False)
    print(f"Assistant: {response}")


if __name__ == "__main__":
    asyncio.run(main())


"""
Sample output:
User: Explain the benefits of an AI model gateway in one paragraph.
Assistant: An AI model gateway provides a unified API layer that routes inference
requests across multiple model providers, enabling organizations to ...
"""
