# Copyright (c) Microsoft. All rights.

import asyncio
import logging
from typing import Any

from agent_framework import AgentRunResponseUpdate, ChatClientAgent, ChatMessage, ChatRole
from agent_framework_workflow import MagenticWorkflowBuilder, WorkflowCompletedEvent
from agent_framework_workflow._magentic import MagenticStartMessage

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def get_real_client() -> Any:
    """Return a real chat client using environment-based config.
    Prefers Azure if AZURE_* settings are present; otherwise uses OpenAI."""
    from agent_framework.openai._chat_client import OpenAIChatClient

    return OpenAIChatClient()


async def main() -> None:
    print("Starting Magentic Workflow Builder Sample")

    # Create specialist agents using ChatClientAgent with a real client
    client = get_real_client()

    researcher = ChatClientAgent(
        name="researcher",
        description="Specialist in research and information gathering",
        chat_client=client,
    )

    writer = ChatClientAgent(
        name="writer",
        description="Specialist in content creation and writing",
        chat_client=client,
    )

    reviewer = ChatClientAgent(
        name="reviewer",
        description="Specialist in quality assurance and review",
        chat_client=client,
    )

    # Callbacks
    async def on_result(final_answer: ChatMessage) -> None:
        print("\n" + "=" * 50)
        print("FINAL RESULT:")
        print("=" * 50)
        print(final_answer.text)
        print("=" * 50)

    def on_exception(exception: Exception) -> None:
        print(f"Exception occurred: {exception}")
        logger.exception("Workflow exception", exc_info=exception)

    async def on_agent_response(agent_id: str, message: ChatMessage) -> None:
        # Non-streaming callback: final messages from orchestrator and agents
        preview = (message.text or "").replace("\n", " ")
        print(f"[on_agent_response] {agent_id}: {message.role.value} -> {preview[:400]}")

    async def on_agent_stream(agent_id: str, update: AgentRunResponseUpdate, is_final: bool) -> None:
        # Streaming callback: incremental agent updates when available
        # Print the agent id once and append chunks on the same line until final.
        nonlocal last_stream_agent_id, stream_line_open

        chunk = getattr(update, "text", None)
        if not chunk:
            try:
                # Fallback: concatenate text from contents if present
                contents = getattr(update, "contents", []) or []
                chunk = "".join(getattr(c, "text", "") for c in contents)
            except Exception:
                chunk = None
        if not chunk:
            return

        # If agent changed, close previous line and start a new header
        if last_stream_agent_id != agent_id or not stream_line_open:
            if stream_line_open:
                print()  # close previous agent's line
            print(f"[on_agent_stream] {agent_id}: ", end="", flush=True)
            last_stream_agent_id = agent_id
            stream_line_open = True

        # Append chunk without starting a new line
        print(chunk, end="", flush=True)

        # On final update, add suffix and newline, and reset
        if is_final:
            print(" (final)")
            stream_line_open = False

    # Build Magentic workflow
    print("\nBuilding Magentic Workflow...")
    builder = MagenticWorkflowBuilder()

    # Add participants
    builder.participants(researcher=researcher, writer=writer, reviewer=reviewer)

    # Set callbacks
    builder.on_result(on_result)
    builder.on_exception(on_exception)
    builder.on_agent_response(on_agent_response)
    builder.on_agent_stream(on_agent_stream)

    last_stream_agent_id: str | None = None
    stream_line_open: bool = False

    builder.with_standard_manager(
        chat_client=client,
        max_round_count=10,
        max_stall_count=3,
        max_reset_count=2,
    )

    # Build the workflow
    workflow = builder.build()
    print("Workflow built successfully!")

    # Create a task for the workflow
    task = ChatMessage(
        role=ChatRole.USER,
        text=(
            "Please write a comprehensive report about the benefits of renewable energy sources. "
            "The report should be well-researched, clearly written, and thoroughly reviewed for accuracy."
        ),
    )

    print(f"\nTask: {task.text}")
    print("\nStarting workflow execution...")

    start_message = MagenticStartMessage(task=task)

    try:
        completion_event = None
        async for event in workflow.run_streaming(start_message):
            print(f"Event: {event}")
            if isinstance(event, WorkflowCompletedEvent):
                completion_event = event

        if completion_event:
            data = getattr(completion_event, "data", None)
            text = getattr(data, "text", None) if data is not None else None
            preview = text if isinstance(text, str) and text else (str(data) if data is not None else "")
            print(f"Workflow completed with result: {preview[:1200]}...")

    except Exception as e:
        print(f"Workflow execution failed: {e}")
        on_exception(e)


if __name__ == "__main__":
    asyncio.run(main())
