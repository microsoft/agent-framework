# Copyright (c) Microsoft. All rights reserved.

import logging
from random import randint
from typing import Annotated

from agent_framework import ChatClientBuilder, ChatMessage, ChatResponse, ChatResponseUpdate

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent_framework")
logger.setLevel(logging.INFO)


def get_weather(
    location: Annotated[str, "The location to get the weather for."],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


class CustomChatClient:
    async def get_response(self, *args, **kwargs):  # type: ignore
        return ChatResponse(messages=[ChatMessage(role="assistant", text="This is a custom chat client response.")])

    async def get_streaming_response(self, *args, **kwargs):  # type: ignore
        yield ChatResponseUpdate(role="assistant", text="This is a custom chat client streaming response.")


async def builder_with_function_and_telemetry():
    """Builder with default Function Calling and Telemetry.

    Telemetry settings will come from the environment.
    """
    print("Custom Chat Client with default Function Calling and Telemetry.")
    # TODO: rebuild function calling and telemetry decorators to work on the protocol level
    # so that they can be applied to custom chat clients as well.
    chat_client = ChatClientBuilder(CustomChatClient).function_calling.open_telemetry.build()

    print((await chat_client.get_response("Hello, what's the weather in Amsterdam?", tools=get_weather)).text)
    # response: The weather in Amsterdam is cloudy with a high of 23°C.

    """
    Output:
    Custom Chat Client with default Function Calling and Telemetry.
[2025-08-27 19:44:47 - INFO] FunctionInvokingChatClient: no _inner_get_response method found on <class 'type'>
[2025-08-27 19:44:47 - INFO] FunctionInvokingChatClient: no _inner_get_streaming_response method found on <class 'type'>
[2025-08-27 19:44:47 - INFO] OpenTelemetryChatClient: no _inner_get_response method found on <class 'type'>
[2025-08-27 19:44:47 - INFO] OpenTelemetryChatClient: no _inner_get_streaming_response method found on <class 'type'>
This is a custom chat client response.
    """


async def run() -> None:
    await builder_with_function_and_telemetry()


if __name__ == "__main__":
    import asyncio

    asyncio.run(run())
