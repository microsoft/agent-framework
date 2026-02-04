# Copyright (c) Microsoft. All rights reserved.

import asyncio
from random import randint
from typing import Annotated

from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential
from pydantic import Field
from agent_framework import tool

"""
Azure Chat Client Direct Usage Example

Demonstrates direct AzureChatClient usage for chat interactions with Azure OpenAI models.
Shows function calling capabilities with custom business logic.
"""

# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production; see samples/getting_started/tools/function_tool_with_approval.py and samples/getting_started/tools/function_tool_with_approval_and_threads.py.
@tool(approval_mode="never_require")
def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def main() -> None:
    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    client = AzureOpenAIChatClient(credential=AzureCliCredential())
    message = "What's the weather in Amsterdam and in Paris?"
    stream = False
    print(f"User: {message}")
    if stream:
        print("Assistant: ", end="")
        async for chunk in client.get_streaming_response(message, tools=get_weather):
            if str(chunk):
                print(str(chunk), end="")
        print("")
    else:
        response = await client.get_response(message, tools=get_weather)
        print(f"Assistant: {response}")


if __name__ == "__main__":
    asyncio.run(main())
