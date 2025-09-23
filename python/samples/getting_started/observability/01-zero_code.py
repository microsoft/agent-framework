# Copyright (c) Microsoft. All rights reserved.
# type: ignore
import asyncio
from random import randint
from typing import TYPE_CHECKING, Annotated

from agent_framework.openai import OpenAIResponsesClient
from pydantic import Field

if TYPE_CHECKING:
    from agent_framework import ChatClientProtocol


"""
This is the simplest sample of using the Agent Framework with telemetry.

This relies on the environment setting up the telemetry, you can test this with
by navigating to this folder and running:
uv run --env-file=zero_code.env opentelemetry-instrument python 01-zero_code.py

Check the zero_code.env file for the settings used in this example and to adapt it to your environment.
"""


async def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    await asyncio.sleep(randint(0, 10) / 10.0)  # Simulate a network call
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def run_chat_client(client: "ChatClientProtocol", stream: bool = False) -> None:
    """Run an AI service.

    This function runs an AI service and prints the output.
    Telemetry will be collected for the service execution behind the scenes,
    and the traces will be sent to the configured telemetry backend.

    The telemetry will include information about the AI service execution.

    Args:
        stream: Whether to use streaming for the plugin

    Remarks:
        When function calling is outside the open telemetry loop
        each of the call to the model is handled as a seperate span,
        while when the open telemetry is put last, a single span
        is shown, which might include one or more rounds of function calling.

        So for the scenario below, you should see the following:

        2 spans with gen_ai.operation.name=chat
            The first has finish_reason "tool_calls"
            The second has finish_reason "stop"
        2 spans with gen_ai.operation.name=execute_tool

    """
    message = "What's the weather in Amsterdam and in Paris?"
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


async def main() -> None:
    client = OpenAIResponsesClient()

    # Scenarios where telemetry is collected in the SDK, from the most basic to the most complex.
    await run_chat_client(client, stream=True)
    await run_chat_client(client, stream=False)


if __name__ == "__main__":
    asyncio.run(main())
