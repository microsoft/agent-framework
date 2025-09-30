# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework.openai import OpenAIChatClient

"""
Chat Response Cancellation Example

This sample demonstrates how to properly cancel streaming chat responses
during execution. The example includes:

- Streaming response initiation with timeout handling
- Proper asyncio task cancellation techniques
- Resource cleanup and error handling
- Graceful interruption of ongoing AI responses
"""


async def main() -> None:
    """
    Demonstrates cancelling a chat request after 1 second.
    Creates a task for the chat request, waits briefly, then cancels it to show proper cleanup.

    Configuration:
    - OpenAI model ID: Use "model_id" parameter or "OPENAI_CHAT_MODEL_ID" environment variable
    - OpenAI API key: Use "api_key" parameter or "OPENAI_API_KEY" environment variable
    """
    chat_client = OpenAIChatClient()

    try:
        task = asyncio.create_task(chat_client.get_response(messages=["Tell me a fantasy story."]))
        await asyncio.sleep(1)
        task.cancel()
        await task
    except asyncio.CancelledError:
        print("Request was cancelled")


if __name__ == "__main__":
    asyncio.run(main())
