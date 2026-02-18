# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Annotated

from agent_framework import Agent, Message, tool
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential

"""
Tool Approvals with Sessions

This sample demonstrates using tool approvals with sessions.
With sessions, you don't need to manually pass previous messages -
the session stores and retrieves them automatically.
"""


@tool(approval_mode="always_require")
def add_to_calendar(
    event_name: Annotated[str, "Name of the event"], date: Annotated[str, "Date of the event"]
) -> str:
    """Add an event to the calendar (requires approval)."""
    print(f">>> EXECUTING: add_to_calendar(event_name='{event_name}', date='{date}')")
    return f"Added '{event_name}' to calendar on {date}"


async def approval_example() -> None:
    """Example showing approval with sessions."""
    print("=== Tool Approval with Session ===\n")

    agent = Agent(
        client=AzureOpenAIChatClient(credential=AzureCliCredential()),
        name="CalendarAgent",
        instructions="You are a helpful calendar assistant.",
        tools=[add_to_calendar],
    )

    session = agent.create_session()

    # Step 1: Agent requests to call the tool
    query = "Add a dentist appointment on March 15th"
    print(f"User: {query}")
    result = await agent.run(query, session=session)

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
            approval_response = request.to_function_approval_response(approved=approved)
            result = await agent.run(Message("user", [approval_response]), session=session)

    print(f"Agent: {result}\n")


async def rejection_example() -> None:
    """Example showing rejection with sessions."""
    print("=== Tool Rejection with Session ===\n")

    agent = Agent(
        client=AzureOpenAIChatClient(credential=AzureCliCredential()),
        name="CalendarAgent",
        instructions="You are a helpful calendar assistant.",
        tools=[add_to_calendar],
    )

    session = agent.create_session()

    query = "Add a team meeting on December 20th"
    print(f"User: {query}")
    result = await agent.run(query, session=session)

    if result.user_input_requests:
        for request in result.user_input_requests:
            print("\nApproval needed:")
            print(f"  Function: {request.function_call.name}")
            print(f"  Arguments: {request.function_call.arguments}")

            # User rejects
            print("  Decision: Rejected")

            # Send rejection response
            rejection_response = request.to_function_approval_response(approved=False)
            result = await agent.run(Message("user", [rejection_response]), session=session)

    print(f"Agent: {result}\n")


async def main() -> None:
    await approval_example()
    await rejection_example()


if __name__ == "__main__":
    asyncio.run(main())
