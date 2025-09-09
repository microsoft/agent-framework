# Copyright (c) Microsoft. All rights reserved.
# type: ignore
import asyncio
import os
from random import randint
from typing import TYPE_CHECKING, Annotated

from agent_framework.openai import OpenAIResponsesClient
from pydantic import Field

if TYPE_CHECKING:
    from agent_framework import ChatClientProtocol


"""
This is the simplest sample of using the Agent Framework with telemetry.
Since it does not create a tracer or span in the script's code, we can let the Agent Framework SDK handle everything.
If the environment variables are set correctly,
the SDK will automatically initialize telemetry and collect traces and logs.
"""


if "AGENT_FRAMEWORK_ENABLE_OTEL" not in os.environ:
    print("Set AGENT_FRAMEWORK_ENABLE_OTEL to enable telemetry with a OTLP endpoint.")
if "AGENT_FRAMEWORK_OTLP_ENDPOINT" not in os.environ and "AGENT_FRAMEWORK_MONITOR_CONNECTION_STRING" not in os.environ:
    print("Set AGENT_FRAMEWORK_OTLP_ENDPOINT or AGENT_FRAMEWORK_MONITOR_CONNECTION_STRING to enable telemetry.")


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
