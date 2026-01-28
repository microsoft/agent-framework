# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import (
    AgentRunUpdateEvent,
    ChatAgent,
    ChatMessage,
    GroupChatBuilder,
    GroupChatState,
    WorkflowOutputEvent,
    tool,
)
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential

"""
Sample: Group Chat with a round-robin speaker selector

What it does:
- Demonstrates the with_orchestrator() API for GroupChat orchestration
- Uses a pure Python function to control speaker selection based on conversation state

Prerequisites:
- OpenAI environment variables configured for OpenAIChatClient
"""


def round_robin_selector(state: GroupChatState) -> str:
    """A round-robin selector function that picks the next speaker based on the current round index."""

    participant_names = list(state.participants.keys())
    return participant_names[state.current_round % len(participant_names)]


async def main() -> None:
    # Create a chat client using Azure OpenAI and Azure CLI credentials for all agents
    chat_client = AzureOpenAIChatClient(credential=AzureCliCredential())

    # Participant agents
    expert = ChatAgent(
        name="PythonExpert",
        instructions=(
            "You are an expert in Python in a workgroup. "
            "Your job is to answer Python related questions and refine your answer "
            "based on feedback from all the other participants."
        ),
        chat_client=chat_client,
    )

    verifier = ChatAgent(
        name="AnswerVerifier",
        instructions=(
            "You are a programming expert in a workgroup. "
            f"Your job is to review the answer provided by {expert.name} and point "
            "out statements that are technically true but practically dangerous."
            "If there is nothing woth pointing out, respond with 'The answer looks good to me.'"
        ),
        chat_client=chat_client,
    )

    clarifier = ChatAgent(
        name="AnswerClarifier",
        instructions=(
            "You are an accessibility expert in a workgroup. "
            f"Your job is to review the answer provided by {expert.name} and point "
            "out jargons or complex terms that may be difficult for a beginner to understand."
            "If there is nothing worth pointing out, respond with 'The answer looks clear to me.'"
        ),
        chat_client=chat_client,
    )

    skeptic = ChatAgent(
        name="Skeptic",
        instructions=(
            "You are a devil's advocate in a workgroup. "
            f"Your job is to review the answer provided by {expert.name} and point "
            "out caveats, exceptions, and alternative perspectives."
            "If there is nothing worth pointing out, respond with 'I have no further questions.'"
        ),
        chat_client=chat_client,
    )

    # Build the group chat workflow
    workflow = (
        GroupChatBuilder()
        .participants([expert, verifier, clarifier, skeptic])
        .with_orchestrator(selection_func=round_robin_selector)
        # Set a hard termination condition: stop after 6 messages (user task + one full rounds + 1)
        # One round is expert -> verifier -> clarifier -> skeptic, after which the expert gets to respond again.
        # This will end the conversation after the expert has spoken 2 times (one iteration loop)
        # Note: it's possible that the expert gets it right the first time and the other participants
        # have nothing to add, but for demo purposes we want to see at least one full round of interaction.
        .with_termination_condition(lambda conversation: len(conversation) >= 6)
        .build()
    )

    task = "How does Python’s Protocol differ from abstract base classes?"

    print("\nStarting Group Chat with round-robin speaker selector...\n")
    print(f"TASK: {task}\n")
    print("=" * 80)

    # Keep track of the last executor to format output nicely in streaming mode
    last_executor_id: str | None = None
    output_event: WorkflowOutputEvent | None = None
    async for event in workflow.run_stream(task):
        if isinstance(event, AgentRunUpdateEvent):
            eid = event.executor_id
            if eid != last_executor_id:
                if last_executor_id is not None:
                    print("\n")
                print(f"{eid}:", end=" ", flush=True)
                last_executor_id = eid
            print(event.data, end="", flush=True)
        elif isinstance(event, WorkflowOutputEvent):
            output_event = event

    # The output of the workflow is the full list of messages exchanged
    if output_event:
        if not isinstance(output_event.data, list) or not all(
            isinstance(msg, ChatMessage)
            for msg in output_event.data  # type: ignore
        ):
            raise RuntimeError("Unexpected output event data format.")
        print("\n" + "=" * 80)
        print("\nFINAL OUTPUT (The conversation history)\n")
        for msg in output_event.data:  # type: ignore
            assert isinstance(msg, ChatMessage)
            print(f"{msg.author_name or msg.role}: {msg.text}\n")
    else:
        raise RuntimeError("Workflow did not produce a final output event.")


if __name__ == "__main__":
    asyncio.run(main())
