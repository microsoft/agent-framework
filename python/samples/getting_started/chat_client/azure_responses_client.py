# Copyright (c) Microsoft. All rights reserved.

import asyncio
from random import randint
from typing import Annotated

from agent_framework import tool
from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import AzureCliCredential
from pydantic import BaseModel

"""
Azure Responses Client Direct Usage Example

Demonstrates direct AzureResponsesClient usage for structured response generation with Azure OpenAI models.
Shows function calling capabilities with custom business logic.
"""


# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production; see samples/getting_started/tools/function_tool_with_approval.py and samples/getting_started/tools/function_tool_with_approval_and_threads.py.
@tool(approval_mode="never_require")
def get_weather(
    location: Annotated[str, "The location to get the weather for."],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


@tool(approval_mode="never_require")
def get_time():
    """Get the current time."""
    from datetime import datetime

    now = datetime.now()
    return f"The current date time is {now.strftime('%Y-%m-%d - %H:%M:%S')}."


class WeatherDetail(BaseModel):
    """Structured output for weather information."""

    location: str
    weather: str


class Weather(BaseModel):
    """Container for multiple outputs."""

    date_time: str
    weather_details: list[WeatherDetail]


async def main() -> None:
    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    client = AzureOpenAIResponsesClient(credential=AzureCliCredential(), api_version="preview")
    message = "What's the weather in Amsterdam and in Paris?"
    stream = True
    print(f"User: {message}")
    response = client.get_response(
        message,
        options={"response_format": Weather, "tools": [get_weather, get_time]},
        stream=stream,
    )
    if stream:
        response = await response.get_final_response()
    else:
        response = await response
    if result := response.value:
        print(f"Assistant: {result.model_dump_json(indent=2)}")
    else:
        print(f"Assistant: {response.text}")


# Expected output (time will be different):
"""
User: What's the weather in Amsterdam and in Paris?
Assistant: {
  "date_time": "2026-02-06 - 13:30:40",
  "weather_details": [
    {
      "location": "Amsterdam",
      "weather": "The weather in Amsterdam is cloudy with a high of 21°C."
    },
    {
      "location": "Paris",
      "weather": "The weather in Paris is sunny with a high of 27°C."
    }
  ]
}
"""


if __name__ == "__main__":
    asyncio.run(main())
