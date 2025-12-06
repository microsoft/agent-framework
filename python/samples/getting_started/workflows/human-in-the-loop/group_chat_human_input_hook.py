# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import (
    ChatMessage,
    GroupChatBuilder,
    HumanInputRequest,
    RequestInfoEvent,
    WorkflowOutputEvent,
    WorkflowRunState,
    WorkflowStatusEvent,
)
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential

"""
Sample: Human Input Hook with GroupChatBuilder

This sample demonstrates using the `.with_human_input_hook()` method to request
arbitrary human feedback mid-workflow with GroupChatBuilder. The hook is called
after each participant takes a turn, allowing human intervention in multi-turn
group conversations.

Purpose:
Show how to use HumanInputRequest to pause a GroupChatBuilder workflow and request
human guidance during a dynamic group conversation.

Demonstrate:
- Configuring a human input hook on GroupChatBuilder
- Monitoring conversation progress and intervening when needed
- Steering group discussions with human input

Prerequisites:
- Azure OpenAI configured for AzureOpenAIChatClient with required environment variables
- Authentication via azure-identity (run az login before executing)
"""

# Track conversation turns for the hook
turn_count = 0


def review_group_discussion(
    conversation: list[ChatMessage],
    agent_id: str | None,
) -> HumanInputRequest | None:
    """Hook that requests human input periodically during group chat.

    This is a simple demonstration using turn counting and keyword detection.
    In practice, you might use other strategies:
    - Always pause after specific participants (by checking agent_id)
    - Pause only when the manager is about to select a critical agent
    - Call an async policy service to determine if review is needed
    - Use sentiment analysis to detect when the discussion needs moderation
    - Return HumanInputRequest unconditionally for mandatory review at every step

    Args:
        conversation: Full conversation history including latest agent response
        agent_id: ID of the agent that just responded

    Returns:
        HumanInputRequest to pause and request input, or None to continue
    """
    global turn_count
    turn_count += 1

    if not conversation:
        return None

    # Check if the conversation is finishing - don't request input if manager said finish
    last_message = conversation[-1]
    text = last_message.text or ""

    # Skip human input if the manager has decided to finish the conversation
    if '"finish":true' in text.replace(" ", "").lower() or '"finish": true' in text.lower():
        return None

    # Example heuristic: request human input every 3 turns
    # This is just one approach - replace with your own logic as needed
    if turn_count % 3 == 0:
        return HumanInputRequest(
            prompt=(
                f"The group has completed {turn_count} turns. "
                "Would you like to provide any guidance or redirect the discussion?"
            ),
            conversation=conversation,
            source_agent_id=agent_id,
            metadata={"turn_count": turn_count},
        )

    # Also request input if the conversation hits a decision point
    decision_keywords = ["disagree", "alternative", "however", "but i think", "on the other hand"]

    if any(keyword in text.lower() for keyword in decision_keywords):
        return HumanInputRequest(
            prompt=(
                f"Agent '{agent_id}' has raised a different perspective. "
                "Would you like to weigh in on this discussion point?"
            ),
            conversation=conversation,
            source_agent_id=agent_id,
            metadata={"trigger": "disagreement", "turn_count": turn_count},
        )

    return None


async def main() -> None:
    chat_client = AzureOpenAIChatClient(credential=AzureCliCredential())

    # Create agents for a group discussion
    optimist = chat_client.create_agent(
        name="optimist",
        instructions=(
            "You are an optimistic team member. You see opportunities and potential "
            "in ideas. Engage constructively with the discussion, building on others' "
            "points while maintaining a positive outlook. Keep responses to 2-3 sentences."
        ),
    )

    pragmatist = chat_client.create_agent(
        name="pragmatist",
        instructions=(
            "You are a pragmatic team member. You focus on practical implementation "
            "and realistic timelines. Sometimes you disagree with overly optimistic views. "
            "Keep responses to 2-3 sentences."
        ),
    )

    creative = chat_client.create_agent(
        name="creative",
        instructions=(
            "You are a creative team member. You propose innovative solutions and "
            "think outside the box. You may suggest alternatives to conventional approaches. "
            "Keep responses to 2-3 sentences."
        ),
    )

    # Manager orchestrates the discussion
    manager = chat_client.create_agent(
        name="manager",
        instructions=(
            "You are a discussion manager. Facilitate the group discussion by acknowledging "
            "contributions and keeping the conversation productive. If human feedback is provided, "
            "incorporate it to guide the discussion. Decide when to conclude after 4-6 exchanges."
        ),
    )

    # Build workflow with human input hook
    workflow = (
        GroupChatBuilder()
        .set_manager(manager=manager, display_name="Discussion Manager")
        .participants([optimist, pragmatist, creative])
        .with_max_rounds(6)
        .with_human_input_hook(review_group_discussion)
        .build()
    )

    # Run the workflow with human-in-the-loop
    pending_responses: dict[str, str] | None = None
    workflow_complete = False

    print("Starting group discussion workflow...")
    print("=" * 60)

    while not workflow_complete:
        # Run or continue the workflow
        stream = (
            workflow.send_responses_streaming(pending_responses)
            if pending_responses
            else workflow.run_stream(
                "Discuss how our team should approach adopting AI tools for productivity. "
                "Consider benefits, risks, and implementation strategies."
            )
        )

        pending_responses = None

        # Process events
        async for event in stream:
            if isinstance(event, RequestInfoEvent):
                if isinstance(event.data, HumanInputRequest):
                    # Display recent conversation
                    print("\n" + "-" * 40)
                    print("HUMAN INPUT REQUESTED")
                    print(f"After turn: {event.data.metadata.get('turn_count', 'unknown')}")
                    if event.data.source_agent_id:
                        print(f"Triggered by: {event.data.source_agent_id}")
                    print("-" * 40)
                    print("Recent discussion:")
                    for msg in event.data.conversation[-4:]:
                        role = msg.role.value if msg.role else "unknown"
                        text = (msg.text or "")[:150]
                        print(f"  [{role}]: {text}...")
                    print("-" * 40)
                    print(f"Prompt: {event.data.prompt}")
                    print("(Discussion paused)")

                    # Get human input
                    user_input = input("Your input (or 'skip' to continue): ")
                    if user_input.lower() == "skip":
                        user_input = "Please continue the discussion naturally."

                    pending_responses = {event.request_id: user_input}
                    print("(Resuming discussion...)")

            elif isinstance(event, WorkflowOutputEvent):
                print("\n" + "=" * 60)
                print("DISCUSSION COMPLETE")
                print("=" * 60)
                print("Final conversation:")
                if event.data:
                    messages: list[ChatMessage] = event.data[-4:]
                    for msg in messages:
                        role = msg.role.value if msg.role else "unknown"
                        text = (msg.text or "")[:200]
                        print(f"[{role}]: {text}...")
                workflow_complete = True

            elif isinstance(event, WorkflowStatusEvent):
                if event.state == WorkflowRunState.IDLE:
                    workflow_complete = True
                # Note: IDLE_WITH_PENDING_REQUESTS is handled inline with RequestInfoEvent


if __name__ == "__main__":
    asyncio.run(main())
