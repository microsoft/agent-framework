# Copyright (c) Microsoft. All rights reserved.

"""Example agent demonstrating human-in-the-loop with function approvals."""

from agent_framework import ChatAgent, ai_function
from agent_framework.azure import AzureOpenAIChatClient

from agent_framework_ag_ui import AgentFrameworkAgent, TaskPlannerConfirmationStrategy


@ai_function(approval_mode="always_require")
def create_calendar_event(title: str, date: str, time: str) -> str:
    """Create a calendar event.

    Args:
        title: The event title
        date: The event date (YYYY-MM-DD)
        time: The event time (HH:MM)

    Returns:
        Confirmation message
    """
    return f"Calendar event '{title}' created for {date} at {time}"


@ai_function(approval_mode="always_require")
def send_email(to: str, subject: str, body: str) -> str:
    """Send an email.

    Args:
        to: Recipient email address
        subject: Email subject
        body: Email body text

    Returns:
        Confirmation message
    """
    return f"Email sent to {to} with subject '{subject}'"


@ai_function(approval_mode="always_require")
def book_meeting_room(room_name: str, date: str, start_time: str, end_time: str) -> str:
    """Book a meeting room.

    Args:
        room_name: The meeting room name
        date: The booking date (YYYY-MM-DD)
        start_time: Start time (HH:MM)
        end_time: End time (HH:MM)

    Returns:
        Confirmation message
    """
    return f"Meeting room '{room_name}' booked for {date} from {start_time} to {end_time}"


agent = ChatAgent(
    name="task_planner",
    instructions=(
        "You are a helpful assistant that plans and executes tasks. "
        "You have access to calendar, email, and meeting room booking functions. "
        "All of these actions require user approval before execution."
    ),
    chat_client=AzureOpenAIChatClient(),
    tools=[create_calendar_event, send_email, book_meeting_room],
)

task_planner_agent = AgentFrameworkAgent(
    agent=agent,
    name="TaskPlanner",
    description="Plans and executes tasks with user approval",
    confirmation_strategy=TaskPlannerConfirmationStrategy(),
)
