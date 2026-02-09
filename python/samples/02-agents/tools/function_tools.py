# Copyright (c) Microsoft. All rights reserved.

import asyncio
from random import randint
from typing import Annotated, Any

from agent_framework import tool
from agent_framework.openai import OpenAIResponsesClient
from pydantic import Field

"""
Function Tools — Advanced Patterns

Demonstrates advanced function tool usage: multiple tools, type annotations with
Pydantic Field, and injecting kwargs (runtime context like user IDs) into tools
without exposing them to the model.

For more on tools:
- Basic tools: ../01-get-started/02_add_tools.py
- Tool approval: ./tool_approval.py
- Tool in a class: getting_started/tools/tool_in_class.py
- Docs: https://learn.microsoft.com/agent-framework/concepts/tools
"""


# <define_tools>
@tool(approval_mode="never_require")
def get_weather(
    location: Annotated[str, Field(description="The city name to get weather for.")],
    units: Annotated[str, Field(description="Temperature units: 'celsius' or 'fahrenheit'.")] = "celsius",
) -> str:
    """Get the current weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    temp = randint(10, 30) if units == "celsius" else randint(50, 86)
    symbol = "°C" if units == "celsius" else "°F"
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {temp}{symbol}."


@tool(approval_mode="never_require")
def get_time(
    timezone: Annotated[str, Field(description="The timezone, e.g. 'US/Pacific', 'Europe/Amsterdam'.")] = "UTC",
) -> str:
    """Get the current time in a given timezone."""
    from datetime import datetime

    return f"The current time in {timezone} is {datetime.now().strftime('%I:%M %p')}."
# </define_tools>


# <tool_with_kwargs>
@tool(approval_mode="never_require")
def get_user_preferences(
    category: Annotated[str, Field(description="The preference category to look up.")],
    **kwargs: Any,
) -> str:
    """Look up a user's preferences. The user_id is injected at runtime via kwargs."""
    user_id = kwargs.get("user_id", "unknown")
    print(f"  [Tool] Looking up '{category}' preferences for user: {user_id}")
    return f"User {user_id} prefers: dark mode, metric units, English language."
# </tool_with_kwargs>


async def main() -> None:
    print("=== Function Tools — Advanced Patterns ===\n")

    # <create_agent>
    agent = OpenAIResponsesClient().as_agent(
        name="AssistantAgent",
        instructions="You are a helpful assistant with access to weather, time, and user preference tools.",
        tools=[get_weather, get_time, get_user_preferences],
    )
    # </create_agent>

    # Multiple tools in one query
    query = "What's the weather in Amsterdam and what time is it there?"
    print(f"User: {query}")
    response = await agent.run(query)
    print(f"Agent: {response}\n")

    # Injecting kwargs — user_id is passed to the tool but not exposed to the model
    # <kwargs_usage>
    query = "What are my display preferences?"
    print(f"User: {query}")
    response = await agent.run(query, user_id="user_42")
    print(f"Agent: {response}\n")
    # </kwargs_usage>


if __name__ == "__main__":
    asyncio.run(main())
