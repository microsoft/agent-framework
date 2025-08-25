# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework.openai import OpenAIChatClient

async def main():
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
