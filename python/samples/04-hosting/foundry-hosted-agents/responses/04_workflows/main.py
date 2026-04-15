# Copyright (c) Microsoft. All rights reserved.

import os

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework.orchestrations import GroupChatBuilder, GroupChatState
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.ai.agentserver.responses import InMemoryResponseProvider
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


def round_robin_selector(state: GroupChatState) -> str:
    """A round-robin selector function that picks the next speaker based on the current round index."""

    participant_names = list(state.participants.keys())
    return participant_names[state.current_round % len(participant_names)]


def main():
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["MODEL_DEPLOYMENT_NAME"],
        credential=AzureCliCredential(),
    )

    writer_agent = Agent(
        client=client,
        instructions=(
            "You are an excellent content writer. You create new content and edit contents based on the feedback."
        ),
        name="writer",
    )

    reviewer_agent = Agent(
        client=client,
        instructions=(
            "You are an excellent content reviewer."
            "Provide actionable feedback to the writer about the provided content."
            "Provide the feedback in the most concise manner possible."
        ),
        name="reviewer",
    )

    workflow_agent = (
        GroupChatBuilder(
            participants=[writer_agent, reviewer_agent],
            # Set a hard termination condition to stop after 4 messages:
            # User message + writer message + reviewer message + writer message
            termination_condition=lambda conversation: len(conversation) >= 4,
            selection_func=round_robin_selector,
        )
        .build()
        .as_agent()
    )

    server = ResponsesHostServer(workflow_agent, store=InMemoryResponseProvider())
    server.run()


if __name__ == "__main__":
    main()
