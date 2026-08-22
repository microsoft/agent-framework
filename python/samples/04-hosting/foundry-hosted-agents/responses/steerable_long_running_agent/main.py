# Copyright (c) Microsoft. All rights reserved.

"""Host a single (non-workflow) agent that counts down slowly, steerably.

The agent is asked to count down from a target number, pacing its own output with a short remark
before each number so a real response takes a while to fully generate. With
`steerable_conversations=True`, sending a new turn on the same conversation while the countdown is
still streaming cancels the in-progress turn and drains the new turn next. Steering is only
supported for non-workflow agents like this one.

Environment variables:
    FOUNDRY_PROJECT_ENDPOINT: Microsoft Foundry project endpoint.
    AZURE_AI_MODEL_DEPLOYMENT_NAME: Model deployment name.
"""

import os

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.ai.agentserver.responses import ResponsesServerOptions
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()


def main() -> None:
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=DefaultAzureCredential(),
    )

    agent = Agent(
        client=client,
        instructions=(
            "You are a counting assistant. When asked to count down from a positive integer, count down one "
            "integer per line, and before each number add a brief, unique one-sentence remark, so your full "
            "response takes some time to generate. If no valid positive integer target is given, reply with "
            "'Please provide a positive integer to count down from.' and nothing else."
        ),
    )

    server = ResponsesHostServer(
        agent,
        options=ResponsesServerOptions(steerable_conversations=True),
        log_level="DEBUG",
    )
    server.run()


if __name__ == "__main__":
    main()
