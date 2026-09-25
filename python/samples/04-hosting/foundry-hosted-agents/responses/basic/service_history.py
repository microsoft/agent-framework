# Copyright (c) Microsoft. All rights reserved.

"""Use downstream service history while retaining outer Responses results."""

import os

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()


def main() -> None:
    agent = Agent(
        client=FoundryChatClient(
            project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            credential=DefaultAzureCredential(),
        ),
        instructions="Be concise.",
        default_options={"store": True},
    )
    ResponsesHostServer(agent=agent, inner_history="service").run()


if __name__ == "__main__":
    main()
