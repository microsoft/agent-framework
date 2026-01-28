# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Annotated

from agent_framework import ChatAgent, ChatMessage, tool
from agent_framework.azure import AzureOpenAIChatClient

"""
Tool Approvals with Threads

This sample demonstrates using tool approvals with threads.
With threads, you don't need to manually pass previous messages -
the thread stores and retrieves them automatically.
"""


@tool(approval_mode="always_require")
def add_to_calendar(
    event_name: Annotated[str, "Name of the event"], date: Annotated[str, "Date of the event"]
) -> str:
    """Add an event to the calendar (requires approval)."""
    print(f">>> EXECUTING: add_to_calendar(event_name='{event_name}', date='{date}')")
    return f"Added '{event_name}' to calendar on {date}"


async def approval_example() -> None:
    """Example showing approval with threads."""
    print("=== Tool Approval with Thread ===\n")

    agent = ChatAgent(
        chat_client=AzureOpenAIChatClient(),
        name="CalendarAgent",
        instructions="You are a helpful calendar assistant.",
        tools=[add_to_calendar],
    )

    thread = agent.get_new_thread()

    # Step 1: Agent requests to call the tool
    query = "Add a dentist appointment on March 15th"
    print(f"User: {query}")
    result = await agent.run(query, thread=thread)

    # Check for approval requests
    if result.user_input_requests:
        for request in result.user_input_requests:
            print("\nApproval needed:")
            print(f"  Function: {request.function_call.name}")
            print(f"  Arguments: {request.function_call.arguments}")

            # User approves (in real app, this would be user input)
            approved = True  # Change to False to see rejection
            print(f"  Decision: {'Approved' if approved else 'Rejected'}")

            # Step 2: Send approval response
            approval_response = request.create_response(approved=approved)
            result = await agent.run(ChatMessage(role="user", contents=[approval_response]), thread=thread)

    print(f"Agent: {result}\n")


async def rejection_example() -> None:
    """Example showing rejection with threads."""
    print("=== Tool Rejection with Thread ===\n")

    agent = ChatAgent(
        chat_client=AzureOpenAIChatClient(),
        name="CalendarAgent",
        instructions="You are a helpful calendar assistant.",
        tools=[add_to_calendar],
    )

    thread = agent.get_new_thread()

    query = "Add a team meeting on December 20th"
    print(f"User: {query}")
    result = await agent.run(query, thread=thread)

    if result.user_input_requests:
        for request in result.user_input_requests:
            print("\nApproval needed:")
            print(f"  Function: {request.function_call.name}")
            print(f"  Arguments: {request.function_call.arguments}")

            # User rejects
            print("  Decision: Rejected")

            # Send rejection response
            rejection_response = request.create_response(approved=False)
            result = await agent.run(ChatMessage(role="user", contents=[rejection_response]), thread=thread)

    print(f"Agent: {result}\n")


async def main() -> None:
    await approval_example()
    await rejection_example()


if __name__ == "__main__":
    asyncio.run(main())
