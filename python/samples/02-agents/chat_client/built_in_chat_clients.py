# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from random import randint
from typing import Annotated, Any, Literal

from agent_framework import SupportsChatGetResponse, tool
from agent_framework.azure import (
    AzureAIAgentClient,
    AzureOpenAIAssistantsClient,
)
from agent_framework.openai import OpenAIAssistantsClient
from azure.identity import AzureCliCredential
from azure.identity.aio import AzureCliCredential as AsyncAzureCliCredential
from pydantic import Field

"""
Built-in Chat Clients Example

This sample demonstrates how to run the same prompt flow against different built-in
chat clients using a single `get_client` factory.

Select one of these client names:
- openai_chat
- openai_responses
- openai_assistants
- anthropic
- ollama
- bedrock
- azure_openai_chat
- azure_openai_responses
- azure_openai_responses_foundry
- azure_openai_assistants
- azure_ai_agent
"""

ClientName = Literal[
    "openai_chat",
    "openai_responses",
    "openai_assistants",
    "anthropic",
    "ollama",
    "bedrock",
    "azure_openai_chat",
    "azure_openai_responses",
    "azure_openai_responses_foundry",
    "azure_openai_assistants",
    "azure_ai_agent",
]


# NOTE: approval_mode="never_require" is for sample brevity.
# Use "always_require" in production; see samples/02-agents/tools/function_tool_with_approval.py
# and samples/02-agents/tools/function_tool_with_approval_and_sessions.py.
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
    from agent_framework.azure import (
        AzureOpenAIChatClient,
        AzureOpenAIResponsesClient,
    )
    from agent_framework.ollama import OllamaChatClient
    from agent_framework.openai import OpenAIChatClient, OpenAIResponsesClient

    # 1. Create OpenAI clients.
    if client_name == "openai_chat":
        return OpenAIChatClient()
    if client_name == "openai_responses":
        return OpenAIResponsesClient()
    if client_name == "openai_assistants":
        return OpenAIAssistantsClient()
    if client_name == "anthropic":
        return AnthropicClient()
    if client_name == "ollama":
        return OllamaChatClient()
    if client_name == "bedrock":
        return BedrockChatClient()

    # 2. Create Azure OpenAI clients.
    if client_name == "azure_openai_chat":
        return AzureOpenAIChatClient(credential=AzureCliCredential())
    if client_name == "azure_openai_responses":
        return AzureOpenAIResponsesClient(credential=AzureCliCredential(), api_version="preview")
    if client_name == "azure_openai_responses_foundry":
        return AzureOpenAIResponsesClient(
            project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
            deployment_name=os.environ["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"],
            credential=AzureCliCredential(),
        )
    if client_name == "azure_openai_assistants":
        return AzureOpenAIAssistantsClient(credential=AzureCliCredential())

    # 3. Create Azure AI client.
    if client_name == "azure_ai_agent":
        return AzureAIAgentClient(credential=AsyncAzureCliCredential())

    raise ValueError(f"Unsupported client name: {client_name}")


async def main(client_name: ClientName = "openai_chat") -> None:
    """Run a basic prompt using a selected built-in client."""
    client = get_client(client_name)

    # 1. Configure prompt and streaming mode.
    message = "What's the weather in Amsterdam and in Paris?"
    stream = os.getenv("STREAM", "false").lower() == "true"
    print(f"Client: {client_name}")
    print(f"User: {message}")

    # 2. Run with context-managed clients.
    if isinstance(client, OpenAIAssistantsClient | AzureOpenAIAssistantsClient | AzureAIAgentClient):
        async with client:
            if stream:
                response_stream = client.get_response(message, stream=True, options={"tools": get_weather})
                print("Assistant: ", end="")
                async for chunk in response_stream:
                    if chunk.text:
                        print(chunk.text, end="")
                print("")
            else:
                print(f"Assistant: {await client.get_response(message, stream=False, options={'tools': get_weather})}")
        return

    # 3. Run with non-context-managed clients.
    if stream:
        response_stream = client.get_response(message, stream=True, options={"tools": get_weather})
        print("Assistant: ", end="")
        async for chunk in response_stream:
            if chunk.text:
                print(chunk.text, end="")
        print("")
    else:
        print(f"Assistant: {await client.get_response(message, stream=False, options={'tools': get_weather})}")


if __name__ == "__main__":
    asyncio.run(main("openai_chat"))


"""
Sample output:
User: What's the weather in Amsterdam and in Paris?
Assistant: The weather in Amsterdam is sunny with a high of 25°C.
...and in Paris it is cloudy with a high of 19°C.
"""
