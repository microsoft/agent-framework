# Copyright (c) Microsoft. All rights reserved.

import asyncio
from datetime import datetime

from agent_framework.ollama import OllamaChatClient
from agent_framework import tool

"""
Ollama Chat Client Example

This sample demonstrates using the native Ollama Chat Client directly.

Ensure to install Ollama and have a model running locally before running the sample.
Not all Models support function calling, to test function calling try llama3.2
Set the model to use via the OLLAMA_MODEL_ID environment variable or modify the code below.
https://ollama.com/

"""

# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production; see samples/getting_started/tools/function_tool_with_approval.py and samples/getting_started/tools/function_tool_with_approval_and_threads.py.
@tool(approval_mode="never_require")
def get_time():
    """Get the current time."""
    return f"The current time is {datetime.now().strftime('%I:%M %p')}."


async def main() -> None:
    client = OllamaChatClient()
    message = "What time is it? Use a tool call"
    stream = False
    print(f"User: {message}")
    if stream:
        print("Assistant: ", end="")
        async for chunk in client.get_streaming_response(message, tools=get_time):
            if str(chunk):
                print(str(chunk), end="")
        print("")
    else:
        response = await client.get_response(message, tools=get_time)
        print(f"Assistant: {response}")


if __name__ == "__main__":
    asyncio.run(main())
