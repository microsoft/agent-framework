# Copyright (c) Microsoft. All rights reserved.

"""Opt into provider background processing without exposing its continuation token."""

import os

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.ai.agentserver.responses import ResponsesServerOptions
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()


def create_agent() -> Agent:
    return Agent(
        client=FoundryChatClient(
            project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            credential=DefaultAzureCredential(),
        ),
        instructions="Write thorough research reports.",
        default_options={"store": True},
    )


def main() -> None:
    ResponsesHostServer(
        agent=create_agent,
        inner_history="service",
        inner_background="provider",
        options=ResponsesServerOptions(resilient_background=True),
    ).run()


if __name__ == "__main__":
    main()
