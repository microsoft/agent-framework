# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from datetime import datetime, timezone
from random import randint
from typing import Annotated

from agent_framework import Agent, tool
from agent_framework.openai import OpenAIChatCompletionClient
from dotenv import load_dotenv
from pydantic import Field

# Load environment variables from .env file
load_dotenv()

"""
aimlapi.com Chat Completion Client with Function Tools Example

This sample demonstrates function tool integration with models served by aimlapi.com,
over a session so the tool-calling loop runs across more than one turn.

The multi-turn case is worth exercising explicitly: several models behind aimlapi.com
reject a literal `"tools": null` in the request body with HTTP 400, which is what a host
sends if it "clears" tools between turns by setting the field to None. Agent Framework
builds request options by omitting unset keys rather than sending nulls
(`_prepare_options` in `agent_framework_openai/_chat_completion_client.py` filters
`v is not None`), so the second turn is a plain request without the key at all.

Environment Variables:
- AIMLAPI_API_KEY: Your aimlapi.com API key (required). Create one at https://aimlapi.com/app/keys
- AIMLAPI_MODEL: The model id to use (optional, defaults to `openai/gpt-4o-mini`).
  Not every model supports tool calling — the catalog at
  https://api.aimlapi.com/v1/models?include=all reports a `capabilities` list per model,
  though it is advisory: some models that do not advertise `tools` support them anyway.
"""

# aimlapi.com speaks the OpenAI Chat Completions wire format at this base URL.
AIMLAPI_BASE_URL = "https://api.aimlapi.com/v1"

# Default model id, chosen because it advertises and supports tool calling.
AIMLAPI_DEFAULT_MODEL = "openai/gpt-4o-mini"

# Attribution headers understood by aimlapi.com. See the basic sample for details.
AIMLAPI_ATTRIBUTION_HEADERS = {
    "HTTP-Referer": "https://github.com/microsoft/agent-framework",
    "X-Title": "Microsoft Agent Framework",
    "X-AIMLAPI-Partner-ID": "part_eIXDWUdHyVKVaVSZNotgkTZ5",
    "X-AIMLAPI-Source": "agent/agent-framework",
}


def create_client() -> OpenAIChatCompletionClient:
    """Build a chat completion client pointed at aimlapi.com."""
    return OpenAIChatCompletionClient(
        model=os.environ.get("AIMLAPI_MODEL", AIMLAPI_DEFAULT_MODEL),
        api_key=os.environ["AIMLAPI_API_KEY"],
        base_url=AIMLAPI_BASE_URL,
        # A fresh dict per client: the module-level constant is never handed out or mutated.
        default_headers={**AIMLAPI_ATTRIBUTION_HEADERS},
    )


# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production;
# see samples/02-agents/tools/function_tool_with_approval.py
# and samples/02-agents/tools/function_tool_with_approval_and_sessions.py.
@tool(approval_mode="never_require")
def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


@tool(approval_mode="never_require")
def get_time() -> str:
    """Get the current UTC time."""
    current_time = datetime.now(timezone.utc)
    return f"The current UTC time is {current_time.strftime('%Y-%m-%d %H:%M:%S')}."


async def multi_turn_tool_calling() -> None:
    """Run two turns over one session, so the second request carries prior tool results."""
    print("=== Multi-turn Tool Calling Example ===")

    agent = Agent(
        client=create_client(),
        name="WeatherAgent",
        instructions="You are a helpful assistant that can report weather and the current time.",
        tools=[get_weather, get_time],
    )

    # A session keeps the message history, so turn 2 replays turn 1's tool call and result.
    session = agent.create_session()

    query1 = "What's the weather like in Seattle?"
    print(f"User: {query1}")
    result1 = await agent.run(query1, session=session)
    print(f"Agent: {result1.text}\n")

    query2 = "And what is the current UTC time? Also remind me which city I just asked about."
    print(f"User: {query2}")
    result2 = await agent.run(query2, session=session)
    print(f"Agent: {result2.text}\n")


async def main() -> None:
    print("=== aimlapi.com Chat Completion Client Agent with Function Tools Example ===\n")

    await multi_turn_tool_calling()


if __name__ == "__main__":
    asyncio.run(main())


"""
Sample output:
=== aimlapi.com Chat Completion Client Agent with Function Tools Example ===

=== Multi-turn Tool Calling Example ===
User: What's the weather like in Seattle?
Agent: The weather in Seattle is cloudy with a high of 18°C.

User: And what is the current UTC time? Also remind me which city I just asked about.
Agent: The current UTC time is 2026-09-03 12:00:00. You just asked about Seattle.
"""
