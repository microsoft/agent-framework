# Copyright (c) Microsoft. All rights reserved.

"""Task steps agent demonstrating agentic generative UI (Feature 6)."""

import asyncio
from collections.abc import AsyncGenerator
from enum import Enum
from typing import Any

from ag_ui.core import (
    EventType,
    MessagesSnapshotEvent,
    RunFinishedEvent,
    StateDeltaEvent,
    StateSnapshotEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
    ToolCallStartEvent,
)
from agent_framework import ChatAgent, ai_function
from agent_framework._clients import ChatClientProtocol
from pydantic import BaseModel, Field

from agent_framework_ag_ui import AgentFrameworkAgent


class StepStatus(str, Enum):
    """Status of a task step."""

    PENDING = "pending"
    COMPLETED = "completed"


class TaskStep(BaseModel):
    """A single step in a task."""

    description: str = Field(
        ..., description="The text of the step in gerund form (e.g., 'Digging hole', 'Opening door')"
    )
    status: StepStatus = Field(default=StepStatus.PENDING, description="The status of the step")


@ai_function
def generate_task_steps(steps: list[TaskStep]) -> str:
    """Generate a list of task steps for completing a task.

    Args:
        steps: Complete list of task steps with descriptions and status

    Returns:
        Confirmation that steps were generated
    """
    return "Steps generated."


def _create_task_steps_agent(chat_client: ChatClientProtocol) -> AgentFrameworkAgent:
    """Create the task steps agent using tool-based approach for streaming.

    Args:
        chat_client: The chat client to use for the agent

    Returns:
        A configured AgentFrameworkAgent instance
    """
    agent = ChatAgent(
        name="task_steps_agent",
        instructions="""You are a helpful assistant that breaks down tasks into actionable steps.

    When asked to perform a task, you MUST:
    1. Use the generate_task_steps tool to create the steps
    2. Pay attention to how many steps the user requests (if specified)
    3. If no specific number is mentioned, use a reasonable number of steps (typically 5-10)
    4. Each step description should be in gerund form (e.g., "Designing spacecraft", "Training astronauts")
    5. Each step should be brief (only 2-4 words)
    6. All steps must have status='pending'
    7. After calling the tool, provide a brief conversational message (one sentence) saying you created the plan

    Example steps for "Build a treehouse in 5 steps":
    - "Selecting location"
    - "Gathering materials"
    - "Assembling frame"
    - "Installing platform"
    - "Adding finishing touches"
    """,
        chat_client=chat_client,
        tools=[generate_task_steps],
    )

    return AgentFrameworkAgent(
        agent=agent,
        name="TaskStepsAgent",
        description="Generates task steps with streaming state updates",
        state_schema={
            "steps": {"type": "array", "description": "The list of task steps"},
        },
        predict_state_config={
            "steps": {
                "tool": "generate_task_steps",
                "tool_argument": "steps",
            }
        },
        require_confirmation=False,  # Agentic generative UI updates automatically without confirmation
    )


# Wrap the agent's run method to add step execution simulation
class TaskStepsAgentWithExecution:
    """Wrapper that adds step execution simulation after plan generation.

    This wrapper delegates to AgentFrameworkAgent but is recognized as compatible
    by add_agent_framework_fastapi_endpoint since it implements run_agent().
    """

    def __init__(self, base_agent: AgentFrameworkAgent):
        """Initialize wrapper with base agent."""
        self._base_agent = base_agent

    @property
    def name(self) -> str:
        """Delegate to base agent."""
        return self._base_agent.name

    @property
    def description(self) -> str:
        """Delegate to base agent."""
        return self._base_agent.description

    def __getattr__(self, name: str) -> Any:
        """Delegate all other attribute access to base agent."""
        return getattr(self._base_agent, name)

    async def run_agent(self, input_data: dict[str, Any]) -> AsyncGenerator[Any, None]:
        """Run the agent and then simulate step execution."""
        import logging
        import uuid

        logger = logging.getLogger(__name__)
        logger.info("TaskStepsAgentWithExecution.run_agent() called - wrapper is active")

        # First, run the base agent to generate the plan - buffer text messages
        final_state: dict[str, Any] = {}
        run_finished_event: Any = None
        tool_call_id: str | None = None
        buffered_text_events: list[Any] = []  # Buffer text from first LLM call

        async for event in self._base_agent.run_agent(input_data):
            event_type_str = str(event.type) if hasattr(event, "type") else type(event).__name__
            logger.info(f"Processing event: {event_type_str}")

            match event:
                case StateSnapshotEvent(snapshot=snapshot):
                    final_state = snapshot.copy() if snapshot else {}
                    logger.info(f"Captured STATE_SNAPSHOT event with state: {final_state}")
                    yield event
                case StateDeltaEvent(delta=delta):
                    # Apply state delta to final_state
                    if delta:
                        for patch in delta:
                            if patch.get("op") == "replace" and patch.get("path") == "/steps":
                                final_state["steps"] = patch.get("value", [])
                                logger.info(
                                    f"Applied STATE_DELTA: updated steps to {len(final_state.get('steps', []))} items"
                                )
                    logger.info(f"Yielding event immediately: {event_type_str}")
                    yield event
                case RunFinishedEvent():
                    run_finished_event = event
                    logger.info("Captured RUN_FINISHED event - will send after step execution and summary")
                case ToolCallStartEvent(tool_call_id=call_id):
                    tool_call_id = call_id
                    logger.info(f"Captured tool_call_id: {tool_call_id}")
                    yield event
                case TextMessageStartEvent() | TextMessageContentEvent() | TextMessageEndEvent():
                    buffered_text_events.append(event)
                    logger.info(f"Buffered {event_type_str} from first LLM call")
                case _:
                    logger.info(f"Yielding event immediately: {event_type_str}")
                    yield event

        logger.info(f"Base agent completed. Final state: {final_state}")

        # Now simulate executing the steps
        if final_state and "steps" in final_state:
            steps = final_state["steps"]
            logger.info(f"Starting step execution simulation for {len(steps)} steps")

            for i in range(len(steps)):
                logger.info(f"Simulating execution of step {i + 1}/{len(steps)}: {steps[i].get('description')}")
                await asyncio.sleep(1.0)  # Simulate work

                # Update step to completed
                steps[i]["status"] = "completed"
                logger.info(f"Step {i + 1} marked as completed")

                # Send delta event with manual JSON patch format
                delta_event = StateDeltaEvent(
                    type=EventType.STATE_DELTA,
                    delta=[
                        {
                            "op": "replace",
                            "path": f"/steps/{i}/status",
                            "value": "completed",
                        }
                    ],
                )
                logger.info(f"Yielding StateDeltaEvent for step {i + 1}")
                yield delta_event

            # Send final snapshot
            final_snapshot = StateSnapshotEvent(
                type=EventType.STATE_SNAPSHOT,
                snapshot={"steps": steps},
            )
            logger.info("Yielding final StateSnapshotEvent with all steps completed")
            yield final_snapshot

            # SECOND LLM call: Stream summary from chat client directly
            logger.info("Making SECOND LLM call to generate summary after step execution")

            # Get the underlying chat agent and client
            chat_agent = self._base_agent.agent  # type: ignore
            chat_client = chat_agent.chat_client  # type: ignore

            # Build messages for summary call
            from agent_framework._types import ChatMessage, TextContent

            original_messages = input_data.get("messages", [])

            # Convert to ChatMessage objects if needed
            messages: list[ChatMessage] = []
            for msg in original_messages:
                if isinstance(msg, dict):
                    content_str = msg.get("content", "")
                    if isinstance(content_str, str):
                        messages.append(
                            ChatMessage(
                                role=msg.get("role", "user"),
                                contents=[TextContent(text=content_str)],
                            )
                        )
                elif isinstance(msg, ChatMessage):
                    messages.append(msg)

            # Add completion message
            messages.append(
                ChatMessage(
                    role="user",
                    contents=[
                        TextContent(
                            text="The steps have been successfully executed. Provide a brief one-sentence summary."
                        )
                    ],
                )
            )

            # Stream the LLM response and manually emit text events
            logger.info("Calling chat client for summary")

            message_id = str(uuid.uuid4())

            try:
                # Emit TEXT_MESSAGE_START
                yield TextMessageStartEvent(
                    type=EventType.TEXT_MESSAGE_START,
                    message_id=message_id,
                    role="assistant",
                )
                # Small delay to ensure START event is processed before CONTENT events
                await asyncio.sleep(0.01)

                # Stream completion
                accumulated_text = ""
                async for chunk in chat_client.get_streaming_response(messages=messages):
                    # chunk is ChatResponseUpdate
                    if hasattr(chunk, "text") and chunk.text:
                        accumulated_text += chunk.text
                        # Emit TEXT_MESSAGE_CONTENT
                        yield TextMessageContentEvent(
                            type=EventType.TEXT_MESSAGE_CONTENT,
                            message_id=message_id,
                            delta=chunk.text,
                        )

                # Emit TEXT_MESSAGE_END
                yield TextMessageEndEvent(
                    type=EventType.TEXT_MESSAGE_END,
                    message_id=message_id,
                )
                logger.info(f"Summary complete: {accumulated_text}")

                # Build complete message for persistence
                summary_message = {
                    "role": "assistant",
                    "content": accumulated_text,
                    "id": message_id,
                }
                final_messages = list(original_messages)
                final_messages.append(summary_message)

                # Emit MessagesSnapshotEvent to persist in history
                yield MessagesSnapshotEvent(
                    type=EventType.MESSAGES_SNAPSHOT,
                    messages=final_messages,
                )
            except Exception as e:
                logger.error(f"Error generating summary: {e}")
                # Generate a new message ID for the error
                error_message_id = str(uuid.uuid4())
                # Yield TEXT_MESSAGE_START for error
                yield TextMessageStartEvent(
                    type=EventType.TEXT_MESSAGE_START,
                    message_id=error_message_id,
                    role="assistant",
                )
                # Yield error message content
                yield TextMessageContentEvent(
                    type=EventType.TEXT_MESSAGE_CONTENT,
                    message_id=error_message_id,
                    delta=f"[Summary generation error: {e!s}]",
                )
                # Yield TEXT_MESSAGE_END for error
                yield TextMessageEndEvent(
                    type=EventType.TEXT_MESSAGE_END,
                    message_id=error_message_id,
                )
        else:
            logger.warning(f"No steps found in final_state to execute. final_state={final_state}")

        # Finally send the original RUN_FINISHED event
        if run_finished_event:
            logger.info("Yielding original RUN_FINISHED event")
            yield run_finished_event


def task_steps_agent_wrapped(chat_client: ChatClientProtocol) -> TaskStepsAgentWithExecution:
    """Create a task steps agent with execution simulation.

    Args:
        chat_client: The chat client to use for the agent

    Returns:
        A wrapped agent instance with step execution simulation
    """
    base_agent = _create_task_steps_agent(chat_client)
    return TaskStepsAgentWithExecution(base_agent)
