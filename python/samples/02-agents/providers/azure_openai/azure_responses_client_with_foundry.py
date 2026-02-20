# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from random import randint
from typing import Annotated

from agent_framework import tool
from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv
from pydantic import Field

# Load environment variables from .env file
load_dotenv()

"""
Azure OpenAI Responses Client with Foundry Project Example

This sample demonstrates how to create an AzureOpenAIResponsesClient using an
Azure AI Foundry project endpoint. Instead of providing an Azure OpenAI endpoint
directly, you provide a Foundry project endpoint and the client is created via
the Azure AI Foundry project SDK.

This requires:
- The `azure-ai-projects` package to be installed.
- The `AZURE_AI_PROJECT_ENDPOINT` environment variable set to your Foundry project endpoint.
- The `AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME` environment variable set to the model deployment name.
"""  # Load environment variables from .env file if present


# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production; see samples/02-agents/tools/function_tool_with_approval.py and samples/02-agents/tools/function_tool_with_approval_and_sessions.py.
@tool(approval_mode="never_require")
def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def non_streaming_example() -> None:
    """Example of non-streaming response (get the complete result at once)."""
    print("=== Non-streaming Response Example ===")

    # 1. Create the AzureOpenAIResponsesClient using a Foundry project endpoint.
    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    credential = AzureCliCredential()
    agent = AzureOpenAIResponsesClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        deployment_name=os.environ["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"],
        credential=credential,
    ).as_agent(
        instructions="You are a helpful weather agent.",
        tools=get_weather,
    )

    # 2. Run a query and print the result.
    query = "What's the weather like in Seattle?"
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Result: {result}\n")


async def streaming_example() -> None:
    """Example of streaming response (get results as they are generated)."""
    print("=== Streaming Response Example ===")

    # 1. Create the AzureOpenAIResponsesClient using a Foundry project endpoint.
    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    credential = AzureCliCredential()
    agent = AzureOpenAIResponsesClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        deployment_name=os.environ["AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME"],
        credential=credential,
    ).as_agent(
        instructions="You are a helpful weather agent.",
        tools=get_weather,
    )

    # 2. Stream the response and print each chunk as it arrives.
    query = "What's the weather like in Portland?"
    print(f"User: {query}")
    print("Agent: ", end="", flush=True)
    async for chunk in agent.run(query, stream=True):
        if chunk.text:
            print(chunk.text, end="", flush=True)
    print("\n")


async def main() -> None:
    print("=== Azure OpenAI Responses Client with Foundry Project Example ===")

    await non_streaming_example()
    await streaming_example()


if __name__ == "__main__":
    asyncio.run(main())


"""
Sample output:
=== Azure OpenAI Responses Client with Foundry Project Example ===
=== Non-streaming Response Example ===
User: What's the weather like in Seattle?
Result: The weather in Seattle is cloudy with a high of 18°C.

=== Streaming Response Example ===
User: What's the weather like in Portland?
Agent: The weather in Portland is sunny with a high of 25°C.
"""
