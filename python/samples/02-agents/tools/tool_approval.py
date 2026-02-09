# Copyright (c) Microsoft. All rights reserved.

import asyncio
from random import randrange
from typing import TYPE_CHECKING, Annotated, Any

from agent_framework import AgentResponse, ChatAgent, ChatMessage, tool
from agent_framework.openai import OpenAIResponsesClient

if TYPE_CHECKING:
    from agent_framework import SupportsAgentRun

"""
Tool Approval — Human-in-the-Loop

Demonstrates requiring user approval before executing sensitive tool calls.
Set `approval_mode="always_require"` on any tool to enable the approval flow.

When approval is required, the agent returns `user_input_requests` instead of
executing the tool. Your code presents the request to the user, collects their
decision, and re-runs the agent with the approval response.

For more on tool approval:
- Approval with threads: getting_started/tools/function_tool_with_approval_and_threads.py
- Docs: https://learn.microsoft.com/agent-framework/concepts/tool-approval
"""

conditions = ["sunny", "cloudy", "raining", "snowing", "clear"]


# <define_tools>
# This tool does NOT require approval
@tool(approval_mode="never_require")
def get_weather(location: Annotated[str, "The city and state, e.g. San Francisco, CA"]) -> str:
    """Get the current weather for a given location."""
    return f"The weather in {location} is {conditions[randrange(0, len(conditions))]} and {randrange(-10, 30)}°C."


# This tool REQUIRES approval before execution
@tool(approval_mode="always_require")
def get_weather_detail(location: Annotated[str, "The city and state, e.g. San Francisco, CA"]) -> str:
    """Get detailed weather forecast for a given location (requires approval)."""
    return (
        f"The weather in {location} is {conditions[randrange(0, len(conditions))]} and {randrange(-10, 30)}°C, "
        f"with a humidity of 88%. "
        f"Tomorrow will be {conditions[randrange(0, len(conditions))]} with a high of {randrange(-10, 30)}°C."
    )
# </define_tools>


# <handle_approvals>
async def handle_approvals(query: str, agent: "SupportsAgentRun") -> AgentResponse:
    """Handle function call approvals without using threads.

    When a tool requires approval, the agent returns user_input_requests.
    We present each request to the user, collect their decision, and re-run.
    """
    result = await agent.run(query)
    while len(result.user_input_requests) > 0:
        new_inputs: list[Any] = [query]

        for request in result.user_input_requests:
            print(
                f"\n⚠️  Approval needed:"
                f"\n  Function: {request.function_call.name}"
                f"\n  Arguments: {request.function_call.arguments}"
            )

            # Add the assistant message with the approval request
            new_inputs.append(ChatMessage("assistant", [request]))

            # Get user approval
            user_approval = await asyncio.to_thread(input, "\nApprove? (y/n): ")

            # Add the user's approval response
            new_inputs.append(
                ChatMessage("user", [request.to_function_approval_response(user_approval.lower() == "y")])
            )

        result = await agent.run(new_inputs)

    return result
# </handle_approvals>


async def main() -> None:
    print("=== Tool Approval — Human-in-the-Loop ===\n")

    # <create_agent>
    async with ChatAgent(
        chat_client=OpenAIResponsesClient(),
        name="WeatherAgent",
        instructions="You are a helpful weather assistant.",
        tools=[get_weather, get_weather_detail],
    ) as agent:
        query = "Get basic weather for LA and detailed weather for Seattle"
        print(f"User: {query}")
        result = await handle_approvals(query, agent)
        print(f"\n{agent.name}: {result}\n")
    # </create_agent>


if __name__ == "__main__":
    asyncio.run(main())
