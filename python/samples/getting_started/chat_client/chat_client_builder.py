# Copyright (c) Microsoft. All rights reserved.

from random import randint
from typing import Annotated

from agent_framework import ChatClientAgent, ChatClientBuilder
from agent_framework.openai import OpenAIResponsesClient


def get_weather(
    location: Annotated[str, "The location to get the weather for."],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def builder_with_function_and_telemetry():
    """Builder with default Function Calling and Telemetry.

    Telemetry settings will come from the environment.
    """
    print("Builder with default Function Calling and Telemetry.")
    chat_client = ChatClientBuilder(OpenAIResponsesClient).function_calling.open_telemetry.build()

    print((await chat_client.get_response("Hello, what's the weather in Amsterdam?", tools=get_weather)).text)
    # response: The weather in Amsterdam is cloudy with a high of 23°C.


async def builder_with_custom_function_and_telemetry():
    print("Builder with Custom Function and Telemetry.")
    chat_client = (
        ChatClientBuilder.chat_client(OpenAIResponsesClient)
        .function_calling_with(max_iterations=5)
        .open_telemetry_with(enable_otel_diagnostics_sensitive=False)
        .build()
    )

    print((await chat_client.get_response("Hello, what's the weather in Amsterdam?", tools=get_weather)).text)
    # response: The weather in Amsterdam is cloudy with a high of 23°C.


async def builder_wo():
    print("Builder without decorators.")
    chat_client = ChatClientBuilder(OpenAIResponsesClient).build()

    print(
        (await chat_client.get_response("Hello, what's the weather in Amsterdam?", tools=get_weather))
        .messages[0]
        .contents[0]
    )
    # response with function call contents, you need to manually execute

    # this is equivalent to
    chat_client = OpenAIResponsesClient()
    print((await chat_client.get_response("Hello, what's the weather in Amsterdam?")).text)
    # response I don't have real-time weather data access. To get the current weather in Amsterdam, I recommend
    # checking a reliable weather service like Weather.com, AccuWeather, or a weather app on your device.
    # Is there anything else I can assist you with?


async def builder_as_context_manager():
    print("Builder as Context Manager")
    async with ChatClientBuilder(OpenAIResponsesClient).function_calling as chat_client:
        print((await chat_client.get_response("Hello, what's the weather in Amsterdam?", tools=get_weather)).text)
        # response: The weather in Amsterdam is sunny with a high of 25°C.


async def agent_with_chat_client_builder():
    """Agent with Chat Client Builder.

    Note that you can pass a builder as well as a ChatClient itself.

    And the agent will check if function invoking is enabled,
    and if not will apply that decorator.
    """
    print("Agent with Chat Client Builder")

    agent = ChatClientAgent(chat_client=ChatClientBuilder(OpenAIResponsesClient).open_telemetry, tools=get_weather)

    print((await agent.run("Hello, what's the weather in Amsterdam?")).text)
    # response: The weather in Amsterdam is sunny with a high of 25°C.


async def run() -> None:
    await agent_with_chat_client_builder()
    await builder_with_function_and_telemetry()
    await builder_wo()
    await builder_as_context_manager()


if __name__ == "__main__":
    import asyncio

    asyncio.run(run())
