# Copyright (c) Microsoft. All rights reserved.

import asyncio
from random import randint
from typing import Annotated

from agent_framework import tool
from agent_framework.openai import OpenAIResponsesClient

"""
Step 2: Add Tools to Your Agent

Give your agent the ability to call functions.
The @tool decorator makes any function available to the agent.

For more on tools, see: ../02-agents/tools/
For docs: https://learn.microsoft.com/agent-framework/get-started/add-tools
"""


# <define_tool>
# approval_mode="never_require" skips human approval for tool calls (optional, default requires approval)
@tool(approval_mode="never_require")
def get_weather(
    location: Annotated[str, "The location to get the weather for."],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."
# </define_tool>


# <create_agent_with_tools>
agent = OpenAIResponsesClient().as_agent(
    name="WeatherAgent",
    instructions="You are a helpful weather agent.",
    tools=get_weather,
)
# </create_agent_with_tools>


async def main():
    # <run_agent>
    response = await agent.run("What's the weather like in Seattle?")
    print(response)
    # </run_agent>


if __name__ == "__main__":
    asyncio.run(main())
