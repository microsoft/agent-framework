# Copyright (c) Microsoft. All rights reserved.

"""
Doubleword Chat Client Example

This sample demonstrates how to use the Microsoft Agent Framework with
Doubleword's OpenAI-compatible inference API. Doubleword is an AI model
gateway providing unified routing, management, and security for inference
across multiple model providers.

Since Doubleword exposes an OpenAI-compatible API, you can use the built-in
OpenAIChatCompletionClient with a custom base URL.

Setup:
    pip install agent-framework-openai
    export DOUBLEWORD_API_KEY="your-api-key"

Available models: https://docs.doubleword.ai/inference-api/models

For batch pricing (up to 90% savings with the Doubleword Inference API),
see https://pypi.org/project/autobatcher/
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


if __name__ == "__main__":
    asyncio.run(main())


"""
Sample output:
User: Explain the benefits of an AI model gateway in one paragraph.
Assistant: An AI model gateway provides a unified API layer that routes inference
requests across multiple model providers, enabling organizations to ...
"""
