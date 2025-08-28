# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework.openai import OpenAIChatClient


async def main() -> None:
    # For OpenAI model ID: Use "ai_model_id" parameter or "OPENAI_CHAT_MODEL_ID" environment variable.
    # For OpenAI API key: Use "api_key" parameter or "OPENAI_API_KEY" environment variable.
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
