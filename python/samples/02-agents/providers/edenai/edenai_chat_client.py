# Copyright (c) Microsoft. All rights reserved.

import asyncio
from datetime import datetime

from agent_framework import Message, tool
from agent_framework.edenai import EdenAIChatClient
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
Eden AI Chat Client Example

This sample demonstrates using the Eden AI chat client directly.

Eden AI is a gateway to many model providers behind one OpenAI compatible API and a
single key. Models use the provider/model format, for example openai/gpt-4o-mini or
anthropic/claude-sonnet-4-5.

Set EDENAI_API_KEY and EDENAI_MODEL in your environment (or pass them to the client),
then run the sample. See https://www.edenai.co to get a key.
"""


# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production;
# see samples/02-agents/tools/function_tool_with_approval.py
# and samples/02-agents/tools/function_tool_with_approval_and_sessions.py.
@tool(approval_mode="never_require")
def get_time():
    """Get the current time."""
    return f"The current time is {datetime.now().strftime('%I:%M %p')}."


async def main() -> None:
    # Reads EDENAI_API_KEY and EDENAI_MODEL from the environment, or pass them here:
    # client = EdenAIChatClient(model="openai/gpt-4o-mini", api_key="...")
    client = EdenAIChatClient()
    message = "What time is it? Use a tool call"
    messages = [Message(role="user", contents=[message])]
    stream = False
    print(f"User: {message}")
    if stream:
        print("Assistant: ", end="")
        async for chunk in client.get_response(messages, options={"tools": [get_time]}, stream=True):
            if str(chunk):
                print(str(chunk), end="")
        print("")
    else:
        response = await client.get_response(messages, options={"tools": [get_time]})
        print(f"Assistant: {response}")


if __name__ == "__main__":
    asyncio.run(main())
