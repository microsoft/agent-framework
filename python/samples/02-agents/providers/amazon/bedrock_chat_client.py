# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Annotated

from agent_framework import Agent, tool
from agent_framework.amazon import BedrockChatClient
from dotenv import load_dotenv
from pydantic import Field

# Load environment variables from .env file
load_dotenv()

"""
Bedrock Chat Client Example

This sample demonstrates using `BedrockChatClient` with an agent and a simple tool.

Environment variables used:
- `BEDROCK_CHAT_MODEL_ID`
- `BEDROCK_REGION` (defaults to `us-east-1` if unset)
- AWS credentials via standard variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`,
  optional `AWS_SESSION_TOKEN`)
"""


# NOTE: approval_mode="never_require" is for sample brevity.
# Use "always_require" in production; see samples/02-agents/tools/function_tool_with_approval.py
# and samples/02-agents/tools/function_tool_with_approval_and_sessions.py.
@tool(approval_mode="never_require")
def get_weather(
    city: Annotated[str, Field(description="The city to get the weather for.")],
) -> dict[str, str]:
    """Return a mock forecast for the requested city."""
    normalized_city = city.strip() or "New York"
    return {"city": normalized_city, "forecast": "72F and sunny"}


async def main() -> None:
    """Run a Bedrock-backed agent with one tool call."""
    # 1. Create an agent with Bedrock chat client and one tool.
    agent = Agent(
        client=BedrockChatClient(),
        instructions="You are a concise travel assistant.",
        name="BedrockWeatherAgent",
        tool_choice="auto",
        tools=[get_weather],
    )

    # 2. Run a query that uses the weather tool.
    query = "Use the weather tool to check the forecast for New York."
    print(f"User: {query}")
    response = await agent.run(query)
    print(f"Assistant: {response.text}")


if __name__ == "__main__":
    asyncio.run(main())


"""
Sample output:
User: Use the weather tool to check the forecast for New York.
Assistant: The forecast for New York is 72F and sunny.
"""
