# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
from random import randint
from typing import Annotated, Literal

from agent_framework import Agent, tool
from typesafe_sdk import Choice, SystemOneResponse

from agent_framework_typesafe import TypeSafeChatClient

"""
Use TypeSafe questions to select and fill a closed-set Agent Framework tool.

Environment variables:
    TYPESAFE_API_KEY — TypeSafe API key.
"""


@tool
def get_weather(
    city: Annotated[Literal["Seattle", "Paris", "Amsterdam"], "City to get the weather for"], detailed: bool
) -> str:
    """Get the weather forecast."""
    suffix = " with a detailed hourly forecast" if detailed else ""
    return f"{city} is sunny and {randint(15, 30)} C{suffix}."


async def main() -> None:
    """Run one TypeSafe-selected function call and print the terminal structured response."""

    async with TypeSafeChatClient(function_invocation_configuration={"max_function_calls": 2}) as client:
        agent = Agent(client=client, name="WeatherEvaluator", tools=[get_weather])
        response = await agent.run(
            "Give me a detailed weather report for Seattle and Amsterdam and tell me where the weather is better.",
            options={
                "response_format": {
                    "better_city": Choice(
                        instructions="Which city has better weather based on the tool results?",
                        criteria={
                            "Seattle": "Seattle has the better weather.",
                            "Amsterdam": "Amsterdam has the better weather.",
                        },
                    )
                }
            },
        )

    if not isinstance(response.value, SystemOneResponse):
        raise RuntimeError("TypeSafe did not return the terminal structured response.")
    print(response.text)


if __name__ == "__main__":
    asyncio.run(main())
