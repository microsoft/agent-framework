# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import asyncio
from random import randint
from typing import Annotated, Any, Literal, cast

from agent_framework import Agent, AgentResponse, tool
from dotenv import load_dotenv
from typesafe_sdk import Choice, SystemOneResponse

from agent_framework_typesafe import TypeSafeChatClient

load_dotenv()

"""
Use TypeSafe questions to select and fill a closed-set Agent Framework tool.

This sample differs from ordinary chat-based function calling:

- The connector creates temporary TypeSafe questions to select the tool and its
  closed-set arguments.
- The user's ``response_format`` questions are evaluated after the tool results
  are available.
- ``response.text`` contains the consolidated tool results plus final ``Choice``
  and ``Score`` decisions.
- ``response.value`` contains the complete typed ``SystemOneResponse``. Use it
  for probabilities, confidence, token usage, and ``Noul`` answers, which are not
  added to the convenience text.

Environment variables:
    TYPESAFE_API_KEY — TypeSafe API key.
"""


@tool
def get_weather(
    city: Annotated[Literal["Seattle", "Paris", "Amsterdam"], "City to get the weather for"],
    detailed: Annotated[bool, "Whether to include a detailed hourly forecast"],
) -> str:
    """Get the weather forecast."""
    suffix = " with a detailed hourly forecast" if detailed else ""
    return f"{city} is sunny and {randint(15, 30)} C{suffix}."


async def main() -> None:
    """Run sequential TypeSafe-selected tool calls and print the consolidated response."""

    # 1. Allow two executions because the user asks about two distinct cities.
    async with TypeSafeChatClient(function_invocation_configuration={"max_function_calls": 2}) as client:
        # 2. Agent Framework supplies the tool. TypeSafe selects its Literal and boolean arguments.
        agent = Agent(client=client, name="WeatherEvaluator", tools=[get_weather])
        response = cast(
            AgentResponse[Any],
            await agent.run(
                "Give me a detailed weather report for Seattle and Amsterdam and tell me where the weather is better.",
                options={
                    # 3. This is a TypeSafe Questions mapping, not a Pydantic output model.
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
            ),
        )

    structured_response = response.value
    if not isinstance(structured_response, SystemOneResponse):
        raise RuntimeError("TypeSafe did not return the terminal structured response.")
    # 4. Readable output is in text; typed probabilities and confidence remain in value.
    print(response.text)
    print(f"Comparison confidence: {structured_response.choices['better_city'].confidence:.3f}")


if __name__ == "__main__":
    asyncio.run(main())


"""
Example output (temperatures and the selected city may vary):

Seattle is sunny and 23 C with a detailed hourly forecast.
Amsterdam is sunny and 25 C.
better_city: Amsterdam
Comparison confidence: 0.940

The first two lines are tool results. The final line in ``response.text`` is the
configured Choice answer. Its probabilities and confidence are available from
``response.value.choices["better_city"]``.
"""
