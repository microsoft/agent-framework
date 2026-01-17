# Copyright (c) Microsoft. All rights reserved.
# ruff: noqa

import asyncio
from random import randint
from typing import TYPE_CHECKING, Annotated

from agent_framework_foundry_local import FoundryLocalClient

if TYPE_CHECKING:
    from agent_framework import ChatAgent

"""
This sample demonstrates basic usage of the FoundryLocalClient.
Shows both streaming and non-streaming responses with function tools.

Running this sample the first time will be slow, as the model needs to be
downloaded and initialized.

Also, not every model supports function calling, so be sure to check the
model capabilities in the Foundry catalog, or pick one from the list printed
when running this sample.
"""


def get_weather(
    location: Annotated[str, "The location to get the weather for."],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def non_streaming_example(agent: "ChatAgent") -> None:
    """Example of non-streaming response (get the complete result at once)."""
    print("=== Non-streaming Response Example ===")

    query = "What's the weather like in Seattle?"
    print(f"User: {query}")
    result = await agent.run(query)
    print(f"Agent: {result}\n")


async def streaming_example(agent: "ChatAgent") -> None:
    """Example of streaming response (get results as they are generated)."""
    print("=== Streaming Response Example ===")

    query = "What's the weather like in Amsterdam?"
    print(f"User: {query}")
    print("Agent: ", end="", flush=True)
    async for chunk in agent.run_stream(query):
        if chunk.text:
            print(chunk.text, end="", flush=True)
    print("\n")


async def main() -> None:
    print("=== Basic Foundry Local Client Agent Example ===")

    client = FoundryLocalClient(model_id="phi-4-mini")
    print(f"Client Model ID: {client.model_id}\n")
    print("Other available models (tool calling supported only):")
    for model in client.manager.list_catalog_models():
        if model.supports_tool_calling:
            print(
                f"- {model.alias} for {model.task} - id={model.id} - {(model.file_size_mb / 1000):.2f} GB - {model.license}"
            )
    agent = client.as_agent(
        name="LocalAgent",
        instructions="You are a helpful agent.",
        tools=get_weather,
    )
    await non_streaming_example(agent)
    await streaming_example(agent)


if __name__ == "__main__":
    asyncio.run(main())
