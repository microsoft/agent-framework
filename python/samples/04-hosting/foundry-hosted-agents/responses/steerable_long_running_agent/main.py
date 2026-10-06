# Copyright (c) Microsoft. All rights reserved.

"""Host a long-running countdown agent while steering is temporarily unavailable.

The agent is asked to count down from a target number, pacing its own output with a short remark
before each number so a response takes a while to fully generate. This sample currently runs
without steering; the hosting layer rejects ``steerable_conversations=True`` until a patched
AgentServer SDK is released and verified.

Environment variables:
    FOUNDRY_PROJECT_ENDPOINT: Microsoft Foundry project endpoint.
    FOUNDRY_MODEL: Model deployment name.
"""

import os

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()


def main() -> None:
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ.get("FOUNDRY_MODEL") or os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
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
        agent=agent,
        history_source="agent_server",
        log_level="DEBUG",
    )
    server.run()


if __name__ == "__main__":
    main()
