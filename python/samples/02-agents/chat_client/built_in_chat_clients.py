# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from random import randint
from typing import Annotated, Any, Literal

from agent_framework import Message, SupportsChatGetResponse, tool
from agent_framework.foundry import FoundryChatClient
from agent_framework.openai import OpenAIChatClient, OpenAIChatCompletionClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv
from pydantic import Field

# Load environment variables from .env file
load_dotenv()

"""
Built-in Chat Clients Example

This sample demonstrates how to run the same prompt flow against different built-in
chat clients using a single `get_client` factory.

Select one of these client names:
- openai_chat
- openai_chat_completion
- anthropic
- ollama
- bedrock
- azure_openai_chat
- azure_openai_chat_completion
- foundry_chat
"""

ClientName = Literal[
    "openai_chat",
    "openai_chat_completion",
    "anthropic",
    "ollama",
    "bedrock",
    "azure_openai_chat",
    "azure_openai_chat_completion",
    "foundry_chat",
]


# NOTE: approval_mode="never_require" is for sample brevity.
@tool(approval_mode="never_require")
def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


def get_client(client_name: ClientName) -> SupportsChatGetResponse[Any]:
    """Create a built-in chat client from a name."""
    from agent_framework.amazon import BedrockChatClient
    from agent_framework.anthropic import AnthropicClient
    from agent_framework.ollama import OllamaChatClient

    if client_name == "openai_chat":
        return OpenAIChatClient()
    if client_name == "openai_chat_completion":
        return OpenAIChatCompletionClient()
    if client_name == "anthropic":
        return AnthropicClient()
    if client_name == "ollama":
        return OllamaChatClient()
    if client_name == "bedrock":
        return BedrockChatClient()
    if client_name == "azure_openai_chat":
        return OpenAIChatClient(credential=AzureCliCredential())
    if client_name == "azure_openai_chat_completion":
        return OpenAIChatCompletionClient(credential=AzureCliCredential())
    if client_name == "foundry_chat":
        return FoundryChatClient(credential=AzureCliCredential())

    raise ValueError(f"Unsupported client name: {client_name}")


async def main(client_name: ClientName = "openai_chat") -> None:
    """Run a basic prompt using a selected built-in client."""
    client = get_client(client_name)

    message = Message("user", contents=["What's the weather in Amsterdam and in Paris?"])
    stream = os.getenv("STREAM", "false").lower() == "true"
    print(f"Client: {client_name}")
    print(f"User: {message.text}")

    if stream:
        response_stream = client.get_response([message], stream=True, options={"tools": get_weather})
        print("Assistant: ", end="")
        async for chunk in response_stream:
            if chunk.text:
                print(chunk.text, end="")
        print("")
    else:
        print(f"Assistant: {await client.get_response([message], stream=False, options={'tools': get_weather})}")


if __name__ == "__main__":
    asyncio.run(main("openai_chat"))


"""
Sample output:
User: What's the weather in Amsterdam and in Paris?
Assistant: The weather in Amsterdam is sunny with a high of 25°C.
...and in Paris it is cloudy with a high of 19°C.
"""
