# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import Message
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
Chat Response Cancellation Example

Demonstrates proper cancellation of streaming chat responses during execution.
Shows asyncio task cancellation and resource cleanup techniques.
"""


async def main() -> None:
    """
    Demonstrates cancelling a chat request after 1 second.
    Creates a task for the chat request, waits briefly, then cancels it to show proper cleanup.

    Configuration:
    - FOUNDRY_PROJECT_ENDPOINT: Azure AI Foundry project endpoint URL
    - FOUNDRY_MODEL: Model deployment name (e.g. gpt-4o)
    - Authentication: Run `az login` to authenticate via AzureCliCredential
    """
    client = FoundryChatClient(credential=AzureCliCredential())

    async def get_story_response() -> None:
        await client.get_response(messages=[Message(role="user", contents=["Tell me a fantasy story."])])

    try:
        task = asyncio.create_task(get_story_response())
        await asyncio.sleep(1)
        task.cancel()
        await task
    except asyncio.CancelledError:
        print("Request was cancelled")


if __name__ == "__main__":
    asyncio.run(main())
