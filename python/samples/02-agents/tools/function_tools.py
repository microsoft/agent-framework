# Copyright (c) Microsoft. All rights reserved.

import asyncio
from random import randint
from typing import Annotated, Any

from agent_framework import FunctionTool, tool
from agent_framework.openai import OpenAIResponsesClient
from pydantic import BaseModel, Field

"""
Function Tools

Demonstrates three patterns for defining function tools:
1. @tool decorator with auto-inferred schema (simplest)
2. @tool decorator with explicit schema (Pydantic model or JSON dict)
3. Declaration-only tool (func=None) — client-side tool the framework cannot execute

For more on tools:
- Basic tools: ../../01-get-started/02_add_tools.py
- Tool approval: ./tool_approval.py
- Docs: https://learn.microsoft.com/agent-framework/agents/tools/function-tools
"""


# --------------------------------------------------------------------------
# Pattern 1: @tool with auto-inferred schema (recommended default)
# --------------------------------------------------------------------------

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


# --------------------------------------------------------------------------
# Pattern 2: @tool with explicit schema
# Use when you need full control over the schema the model sees,
# or when the function signature doesn't match the desired schema.
# --------------------------------------------------------------------------

# <explicit_schema_pydantic>
class LocationInput(BaseModel):
    """Input schema using a Pydantic model."""

    location: Annotated[str, Field(description="The city name to get weather for")]
    unit: Annotated[str, Field(description="Temperature unit: celsius or fahrenheit")] = "celsius"


@tool(
    name="get_weather_explicit",
    description="Get the current weather for a given location.",
    schema=LocationInput,
    approval_mode="never_require",
)
def get_weather_explicit(location: str, unit: str = "celsius") -> str:
    """Get the current weather for a location (explicit schema)."""
    return f"The weather in {location} is 22 degrees {unit}."
# </explicit_schema_pydantic>


# <explicit_schema_dict>
time_schema = {
    "type": "object",
    "properties": {
        "timezone": {"type": "string", "description": "Timezone to get the current time for", "default": "UTC"},
    },
}


@tool(
    name="get_time_explicit",
    description="Get the current time in a given timezone.",
    schema=time_schema,
    approval_mode="never_require",
)
def get_time_explicit(timezone: str = "UTC") -> str:
    """Get the current time (explicit JSON schema)."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    return f"The current time in {timezone} is {datetime.now(ZoneInfo(timezone)).isoformat()}"
# </explicit_schema_dict>


# --------------------------------------------------------------------------
# Pattern 3: Declaration-only tool (func=None)
# The schema is sent to the model, but the framework has no implementation.
# Useful when the caller must supply the result (e.g. client-side GPS lookup).
# --------------------------------------------------------------------------

# <declaration_only_tool>
get_user_location = FunctionTool(
    name="get_user_location",
    func=None,  # no implementation — caller must supply the result
    description="Get the user's current city. Only the client application can resolve this.",
    input_model={
        "type": "object",
        "properties": {
            "reason": {"type": "string", "description": "Why the location is needed"},
        },
        "required": ["reason"],
    },
)
# </declaration_only_tool>


async def main() -> None:
    print("=== Pattern 1: Auto-inferred schema ===\n")

    # <create_agent>
    agent = OpenAIResponsesClient().as_agent(
        name="AssistantAgent",
        instructions="You are a helpful assistant with access to weather, time, and user preference tools.",
        tools=[get_weather, get_time, get_user_preferences],
    )
    # </create_agent>

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

    print("=== Pattern 2: Explicit schema ===\n")

    agent2 = OpenAIResponsesClient().as_agent(
        name="ExplicitSchemaAgent",
        instructions="You are a helpful assistant.",
        tools=[get_weather_explicit, get_time_explicit],
    )
    response = await agent2.run("What is the weather in Seattle and what time is it?")
    print(f"Agent: {response}\n")

    # Pattern 3 (declaration-only) is best demonstrated in a workflow context —
    # see 03-workflows/human-in-the-loop/agents_with_declaration_only_tools.py
    print("=== Pattern 3: Declaration-only tool ===")
    print(f"Tool name: {get_user_location.name}")
    print(f"Has implementation: {get_user_location.func is not None}")
    print("(See 03-workflows/human-in-the-loop/agents_with_declaration_only_tools.py for full usage)\n")


if __name__ == "__main__":
    asyncio.run(main())
