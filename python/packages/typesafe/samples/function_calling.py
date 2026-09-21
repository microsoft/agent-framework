# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
from typing import Any, Literal, cast

from agent_framework import Agent, FunctionTool
from pydantic import BaseModel
from typesafe_sdk import Noul, SystemOneResponse

from agent_framework_typesafe import TypeSafeChatClient

"""
Use TypeSafe questions to select and fill a closed-set Agent Framework tool.

Environment variables:
    TYPESAFE_API_KEY — TypeSafe API key.
"""


class WeatherArguments(BaseModel):
    """Arguments TypeSafe can fill using Choice and Noul questions."""

    city: Literal["Seattle", "Paris"]
    detailed: bool


def get_weather(city: str, detailed: bool) -> str:
    """Return deterministic sample weather."""
    suffix = " with a detailed hourly forecast" if detailed else ""
    return f"{city} is sunny and 22 C{suffix}."


async def main() -> None:
    """Run one TypeSafe-selected function call and print the terminal structured response."""
    weather = FunctionTool(
        name="get_weather",
        description="Get weather for Seattle or Paris.",
        func=get_weather,
        input_model=WeatherArguments,
    )

    async with TypeSafeChatClient() as client:
        agent = Agent(client=client, name="WeatherEvaluator", tools=[weather])
        response = await agent.run(
            "Give me a detailed weather report for Seattle.",
            options=cast(
                Any,
                {
                    "response_format": {
                        "succeeded": Noul(instructions="Did the tool result contain a successful weather report?")
                    }
                },
            ),
        )

    if not isinstance(response.value, SystemOneResponse):
        raise RuntimeError("TypeSafe did not return the terminal structured response.")
    print(response.text)


if __name__ == "__main__":
    asyncio.run(main())
