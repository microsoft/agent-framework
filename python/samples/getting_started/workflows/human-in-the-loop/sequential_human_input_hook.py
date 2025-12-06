# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import (
    ChatMessage,
    HumanInputRequest,
    RequestInfoEvent,
    SequentialBuilder,
    WorkflowOutputEvent,
    WorkflowRunState,
    WorkflowStatusEvent,
)
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential

"""
Sample: Human Input Hook with SequentialBuilder

This sample demonstrates using the `.with_human_input_hook()` method to request
arbitrary human feedback mid-workflow with high-level builders. Unlike tool approval
(binary approve/deny), human input hooks allow injecting custom guidance into the
conversation.

Purpose:
Show how to use HumanInputRequest to pause a SequentialBuilder workflow and request
human review or additional input before continuing to the next agent.

Demonstrate:
- Configuring a human input hook that triggers based on conversation content
- Handling RequestInfoEvent with HumanInputRequest data
- Injecting human responses back into the workflow via send_responses_streaming

Prerequisites:
- Azure OpenAI configured for AzureOpenAIChatClient with required environment variables
- Authentication via azure-identity (run az login before executing)
"""


def request_review_on_keyword(
    conversation: list[ChatMessage],
    agent_id: str | None,
) -> HumanInputRequest | None:
    """Hook that requests human input when an agent mentions 'review'.

    This is a simple demonstration heuristic that triggers on keyword matches.
    In practice, you might use other strategies:
    - Always pause after specific agents (by checking agent_id)
    - Pause every N steps using a counter
    - Call an async policy service to determine if review is needed
    - Use content classification to detect sensitive topics
    - Return HumanInputRequest unconditionally for mandatory review at every step

    Args:
        conversation: Full conversation history including agent's latest response
        agent_id: ID of the agent that just responded

    Returns:
        HumanInputRequest to pause and request input, or None to continue
    """
    if not conversation:
        return None

    # Example heuristic: check the last message for keywords suggesting review is needed
    # This is just one approach - replace with your own logic as needed
    last_message = conversation[-1]
    text = last_message.text or ""
    keywords = ["review", "confirm", "approve", "feedback", "check"]

    if any(keyword in text.lower() for keyword in keywords):
        return HumanInputRequest(
            prompt=f"Agent '{agent_id}' is requesting your review. Please provide feedback:",
            conversation=conversation,
            source_agent_id=agent_id,
            metadata={"trigger": "keyword_match"},
        )
    return None


async def main() -> None:
    chat_client = AzureOpenAIChatClient(credential=AzureCliCredential())

    # Create agents for a sequential document review workflow
    drafter = chat_client.create_agent(
        name="drafter",
        instructions=(
            "You are a document drafter. When given a topic, create a brief draft "
            "(2-3 sentences). Always end with 'Please review this draft and provide feedback.'"
        ),
    )

    editor = chat_client.create_agent(
        name="editor",
        instructions=(
            "You are an editor. Review the draft and suggest improvements. "
            "Incorporate any human feedback that was provided. "
            "Always end with 'Please confirm these edits are acceptable.'"
        ),
    )

    finalizer = chat_client.create_agent(
        name="finalizer",
        instructions=(
            "You are a finalizer. Take the edited content and create a polished final version. "
            "Incorporate any additional feedback provided. "
            "Present the final document without asking for review."
        ),
    )

    # Build workflow with human input hook
    workflow = (
        SequentialBuilder()
        .participants([drafter, editor, finalizer])
        .with_human_input_hook(request_review_on_keyword)
        .build()
    )

    # Run the workflow with human-in-the-loop
    pending_responses: dict[str, str] | None = None
    workflow_complete = False

    print("Starting document review workflow...")
    print("=" * 60)

    while not workflow_complete:
        # Run or continue the workflow
        stream = (
            workflow.send_responses_streaming(pending_responses)
            if pending_responses
            else workflow.run_stream("Write a brief introduction to artificial intelligence.")
        )

        pending_responses = None

        # Process events
        async for event in stream:
            if isinstance(event, RequestInfoEvent):
                if isinstance(event.data, HumanInputRequest):
                    # Display the conversation context
                    print("\n" + "-" * 40)
                    print("HUMAN INPUT REQUESTED")
                    print(f"From agent: {event.data.source_agent_id}")
                    print("-" * 40)
                    print("Recent conversation:")
                    for msg in event.data.conversation[-3:]:
                        role = msg.role.value if msg.role else "unknown"
                        text = (msg.text or "")[:200]
                        print(f"  [{role}]: {text}...")
                    print("-" * 40)
                    print(f"Prompt: {event.data.prompt}")
                    print("(Workflow paused)")

                    # Get human input
                    user_input = input("Your feedback (or 'skip' to continue): ")  # noqa: ASYNC250
                    if user_input.lower() == "skip":
                        user_input = "Looks good, please continue."

                    pending_responses = {event.request_id: user_input}
                    print("(Resuming workflow...)")

            elif isinstance(event, WorkflowOutputEvent):
                print("\n" + "=" * 60)
                print("WORKFLOW COMPLETE")
                print("=" * 60)
                print("Final output:")
                if event.data:
                    messages: list[ChatMessage] = event.data[-3:]
                    for msg in messages:
                        role = msg.role.value if msg.role else "unknown"
                        print(f"[{role}]: {msg.text}")
                workflow_complete = True

            elif isinstance(event, WorkflowStatusEvent) and event.state == WorkflowRunState.IDLE:
                workflow_complete = True
                # Note: IDLE_WITH_PENDING_REQUESTS is handled inline with RequestInfoEvent


if __name__ == "__main__":
    asyncio.run(main())
