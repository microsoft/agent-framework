# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import cast

from agent_framework import (
    AgentResponseUpdate,
    ChatAgent,
    ChatMessage,
)
from agent_framework.azure import AzureOpenAIChatClient
from agent_framework.orchestrations import GroupChatBuilder, GroupChatState
from azure.identity import AzureCliCredential

"""
Sample: Group Chat with a round-robin speaker selector

What it does:
- Demonstrates the selection_func parameter for GroupChat orchestration
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
    # termination_condition: stop after 6 messages (user task + one full rounds + 1)
    # One round is expert -> verifier -> clarifier -> skeptic, after which the expert gets to respond again.
    # This will end the conversation after the expert has spoken 2 times (one iteration loop)
    # Note: it's possible that the expert gets it right the first time and the other participants
    # have nothing to add, but for demo purposes we want to see at least one full round of interaction.
    # intermediate_outputs=True: Enable intermediate outputs to observe the conversation as it unfolds
    # (Intermediate outputs will be emitted as WorkflowOutputEvent events)
    workflow = (
        GroupChatBuilder(
            participants=[expert, verifier, clarifier, skeptic],
            termination_condition=lambda conversation: len(conversation) >= 6,
            intermediate_outputs=True,
            selection_func=round_robin_selector,
        )
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

    # Keep track of the last response to format output nicely in streaming mode
    last_response_id: str | None = None
    async for event in workflow.run(task, stream=True):
        if event.type == "output":
            data = event.data
            if isinstance(data, AgentResponseUpdate):
                rid = data.response_id
                if rid != last_response_id:
                    if last_response_id is not None:
                        print("\n")
                    print(f"{data.author_name}:", end=" ", flush=True)
                    last_response_id = rid
                print(data.text, end="", flush=True)
            elif event.type == "output":
                # The output of the group chat workflow is a collection of chat messages from all participants
                outputs = cast(list[ChatMessage], event.data)
                print("\n" + "=" * 80)
                print("\nFinal Conversation Transcript:\n")
                for message in outputs:
                    print(f"{message.author_name or message.role}: {message.text}\n")


if __name__ == "__main__":
    asyncio.run(main())
