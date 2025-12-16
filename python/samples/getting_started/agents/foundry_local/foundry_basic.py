# Copyright (c) Microsoft. All rights reserved.

import asyncio
from random import randint
from typing import Annotated

from agent_framework_foundry_local import FoundryLocalChatClient

"""
This sample demonstrates basic usage of the FoundryLocalChatClient.
Shows both streaming and non-streaming responses with function tools.

Running this sample the first time will be slow, as the model needs to be
downloaded and initialized.

Also, not every model supports function calling, so be sure to check the
model capabilities in the Foundry catalog.
"""


def get_weather(
    location: Annotated[str, "The location to get the weather for."],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def non_streaming_example(client: FoundryLocalChatClient) -> None:
    """Example of non-streaming response (get the complete result at once)."""
    print("=== Non-streaming Response Example ===")

    # Since no Agent ID is provided, the agent will be automatically created
    # and deleted after getting a response
    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.

    agent = client.create_agent(
        name="LocalAgent",
        instructions="You are a helpful agent.",
        tools=get_weather,
    )
    query = "What's the weather like in Seattle?"
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Agent: {result}\n")


async def streaming_example(client: FoundryLocalChatClient) -> None:
    """Example of streaming response (get results as they are generated)."""
    print("=== Streaming Response Example ===")

    agent = client.create_agent(
        name="LocalAgent",
        instructions="You are a helpful agent.",
        tools=get_weather,
    )
    query = "What's the weather like in Amsterdam?"
    print(f"User: {query}")
    print("Agent: ", end="", flush=True)
    async for chunk in agent.run_stream(query):
        if chunk.text:
            print(chunk.text, end="", flush=True)
    print("\n")


async def main() -> None:
    print("=== Basic Foundry Chat Client Agent Example ===")

    client = FoundryLocalChatClient(model_id="phi-4-mini")
    print(f"Client Model ID: {client.model_id}\n")
    print("Other available models:")
    for model in client.manager.list_catalog_models():
        print(
            f"- {model.alias} for {model.task} - id={model.id} - {(model.file_size_mb / 1000):.2f} GB - {model.license}"
        )

    await non_streaming_example(client)
    await streaming_example(client)


if __name__ == "__main__":
    asyncio.run(main())
