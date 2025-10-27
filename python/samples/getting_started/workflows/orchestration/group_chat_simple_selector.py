# Copyright (c) Microsoft. All rights reserved.

import asyncio
import logging

from agent_framework import ChatAgent, GroupChatBuilder, GroupChatStateSnapshot, WorkflowOutputEvent
from agent_framework.openai import OpenAIChatClient

logging.basicConfig(level=logging.INFO)

"""
Sample: Group Chat with Simple Speaker Selector Function

What it does:
- Demonstrates the select_speakers() API for GroupChat orchestration
- Uses a pure Python function to control speaker selection based on conversation state
- Alternates between researcher and writer agents in a simple round-robin pattern
- Shows how to access conversation history, round index, and participant metadata

Key pattern:
    def select_next_speaker(state: GroupChatStateSnapshot) -> str | None:
        # state contains: task, participants, conversation, history, round_index
        # Return participant name to continue, or None to finish
        ...

Prerequisites:
- OpenAI environment variables configured for OpenAIChatClient
"""


def select_next_speaker(state: GroupChatStateSnapshot) -> str | None:
    """Simple speaker selector that alternates between researcher and writer.

    This function demonstrates the core pattern:
    1. Examine the current state of the group chat
    2. Decide who should speak next
    3. Return participant name or None to finish

    Args:
        state: Immutable snapshot containing:
            - task: ChatMessage - original user task
            - participants: dict[str, str] - participant names → descriptions
            - conversation: tuple[ChatMessage, ...] - full conversation history
            - history: tuple[GroupChatTurn, ...] - turn-by-turn with speaker attribution
            - round_index: int - number of selection rounds so far
            - pending_agent: str | None - currently active agent (if any)

    Returns:
        Name of next speaker, or None to finish the conversation
    """
    round_idx = state["round_index"]
    history = state["history"]

    # Finish after 4 turns (researcher → writer → researcher → writer)
    if round_idx >= 4:
        return None

    # Get the last speaker from history
    last_speaker = history[-1].speaker if history else None

    # Simple alternation: researcher → writer → researcher → writer
    if last_speaker == "Researcher":
        return "Writer"
    return "Researcher"


async def main() -> None:
    researcher = ChatAgent(
        name="Researcher",
        description="Collects relevant background information.",
        instructions="Gather concise facts that help answer the question. Be brief.",
        chat_client=OpenAIChatClient(model_id="gpt-4o-mini"),
    )

    writer = ChatAgent(
        name="Writer",
        description="Synthesizes a polished answer using the gathered notes.",
        instructions="Compose a clear, structured answer using any notes provided.",
        chat_client=OpenAIChatClient(model_id="gpt-4o-mini"),
    )

    # Two ways to specify participants:
    # 1. List form - uses agent.name attribute: .participants([researcher, writer])
    # 2. Dict form - explicit names: .participants(researcher=researcher, writer=writer)
    workflow = (
        GroupChatBuilder()
        .select_speakers(select_next_speaker, display_name="Orchestrator")
        .participants([researcher, writer])  # Uses agent.name for participant names
        .build()
    )

    task = "What are the key benefits of using async/await in Python?"

    print("\nStarting Group Chat with Simple Speaker Selector...\n")
    print(f"TASK: {task}\n")
    print("=" * 80)

    async for event in workflow.run_stream(task):
        if isinstance(event, WorkflowOutputEvent):
            final_message = event.data
            author = getattr(final_message, "author_name", "Unknown")
            text = getattr(final_message, "text", str(final_message))
            print(f"\n[{author}]\n{text}\n")
            print("-" * 80)

    print("\nWorkflow completed.")


if __name__ == "__main__":
    asyncio.run(main())
