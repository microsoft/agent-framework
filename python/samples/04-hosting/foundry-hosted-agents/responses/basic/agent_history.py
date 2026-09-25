# Copyright (c) Microsoft. All rights reserved.

"""Use MAF history in AgentSession instead of replaying Responses history."""

import os

from agent_framework import Agent, InMemoryHistoryProvider
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
        context_providers=[InMemoryHistoryProvider()],
        default_options={"store": False},
    )
    ResponsesHostServer(agent=agent, inner_history="agent").run()


if __name__ == "__main__":
    main()
