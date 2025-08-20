# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import CancellationToken
from agent_framework.openai import OpenAIChatClient

async def main():
    cancellation_token = CancellationToken()
    chat_client = OpenAIChatClient()

    try:
        message = chat_client.get_response(messages=["Tell me a long story about AI."], cancellation_token=cancellation_token)
        await asyncio.sleep(1)
        cancellation_token.cancel()
        await message
    except asyncio.CancelledError:
        print("Request was cancelled")

if __name__ == "__main__":
    asyncio.run(main())
