# Copyright (c) Microsoft. All rights reserved.
"""Implement a function tool for OpenAI Assistants in SK and AF."""

import asyncio
import os
from typing import Any

ASSISTANT_MODEL = os.environ.get("OPENAI_ASSISTANT_MODEL", "gpt-4o-mini")


async def fake_weather_lookup(city: str, day: str) -> dict[str, Any]:
    """Pretend to call a weather service."""
    return {
        "city": city,
        "day": day,
        "forecast": "Sunny with scattered clouds",
        "high_c": 22,
        "low_c": 14,
    }


async def run_semantic_kernel() -> None:
    from semantic_kernel.agents import AssistantAgentThread, OpenAIAssistantAgent
    from semantic_kernel.functions import kernel_function

    class WeatherPlugin:
        @kernel_function(name="get_forecast", description="Look up the forecast for a city and day.")
        async def fake_weather_lookup(city: str, day: str) -> dict[str, Any]:
            """Pretend to call a weather service."""
            return {
                "city": city,
                "day": day,
                "forecast": "Sunny with scattered clouds",
                "high_c": 22,
                "low_c": 14,
            }

    client = OpenAIAssistantAgent.create_client()
    # Tool schema is registered on the assistant definition.
    definition = await client.beta.assistants.create(
        model=ASSISTANT_MODEL,
        name="WeatherHelper",
        instructions="Call get_forecast to fetch weather details.",
        plugins=[WeatherPlugin()],
    )
    agent = OpenAIAssistantAgent(client=client, definition=definition)

    thread: AssistantAgentThread | None = None
    response = await agent.get_response(
        "What will the weather be like in Seattle tomorrow?",
        thread=thread,
    )
    thread = response.thread
    print("[SK][initial]", response.message.content)


async def run_agent_framework() -> None:
    from agent_framework._tools import tool
    from agent_framework.openai import OpenAIAssistantsClient

    @tool(
        name="get_forecast",
        description="Look up the forecast for a city and day.",
    )
    async def get_forecast(city: str, day: str) -> dict[str, Any]:
        return await fake_weather_lookup(city, day)

    assistants_client = OpenAIAssistantsClient()
    # AF converts the decorated function into an assistant-compatible tool.
    async with assistants_client.as_agent(
        name="WeatherHelper",
        instructions="Call get_forecast to fetch weather details.",
        model=ASSISTANT_MODEL,
        tools=[get_forecast],
    ) as assistant_agent:
        reply = await assistant_agent.run(
            "What will the weather be like in Seattle tomorrow?",
            tool_choice="auto",
        )
        print("[AF]", reply.text)


async def main() -> None:
    await run_semantic_kernel()
    await run_agent_framework()


if __name__ == "__main__":
    asyncio.run(main())
