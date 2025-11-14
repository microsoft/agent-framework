# Copyright (c) Microsoft. All rights reserved.

"""Human-in-the-loop agent demonstrating step customization (Feature 5)."""

from enum import Enum

from agent_framework import ChatAgent, ai_function
from agent_framework._clients import ChatClientProtocol
from pydantic import BaseModel, Field


class StepStatus(str, Enum):
    """Status of a task step."""

    ENABLED = "enabled"
    DISABLED = "disabled"


class TaskStep(BaseModel):
    """A single step in a task execution plan."""

    description: str = Field(..., description="The text of the step in imperative form (e.g., 'Dig hole', 'Open door')")
    status: StepStatus = Field(default=StepStatus.ENABLED, description="Whether the step is enabled or disabled")


@ai_function(
    name="generate_task_steps",
    description="Generate execution steps for a task",
    approval_mode="always_require",
)
def generate_task_steps(steps: list[TaskStep]) -> str:
    """Make up 10 steps (only a couple of words per step) that are required for a task.

    The step should be in imperative form (i.e. Dig hole, Open door, ...).
    Each step will have status='enabled' by default.

    Args:
        steps: An array of 10 step objects, each containing description and status

    Returns:
        Confirmation message
    """
    return f"Generated {len(steps)} execution steps for the task."


def human_in_the_loop_agent(chat_client: ChatClientProtocol) -> ChatAgent:
    """Create a human-in-the-loop agent using tool-based approach for predictive state.

    Args:
        chat_client: The chat client to use for the agent

    Returns:
        A configured ChatAgent instance with human-in-the-loop capabilities
    """
    return ChatAgent(
        name="human_in_the_loop_agent",
        instructions="""You are a helpful assistant that can perform any task by breaking it down into steps.

    When asked to perform a task, you MUST call the `generate_task_steps` function with the proper
    number of steps per the request.

    Rules for steps:
    - Each step description should be in imperative form (e.g., "Dig hole", "Open door", "Prepare ingredients")
    - Each step should be brief (only a couple of words)
    - All steps must have status='enabled' initially

    Example steps for "Build a robot":
    1. "Design blueprint"
    2. "Gather components"
    3. "Assemble frame"
    4. "Install motors"
    5. "Wire electronics"
    6. "Program controller"
    7. "Test movements"
    8. "Add sensors"
    9. "Calibrate systems"
    10. "Final testing"

    After calling the function, provide a brief acknowledgment like:
    "I've created a plan with 10 steps. You can customize which steps to enable before I proceed."
    """,
        chat_client=chat_client,
        tools=[generate_task_steps],
    )
