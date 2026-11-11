# Copyright (c) Microsoft. All rights reserved.

"""Opt into provider background processing without exposing its continuation token."""

import os

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer, ResponsesRequest
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()


def create_agent(*, request: ResponsesRequest) -> Agent:
    return Agent(
        client=FoundryChatClient(
            project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            model=os.environ.get("FOUNDRY_MODEL") or os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            credential=DefaultAzureCredential(),
        ),
        instructions="Write thorough research reports.",
        default_options={"store": True},
    )


def main() -> None:
    ResponsesHostServer(
        agent=create_agent,
        history_source="inference_service",
        background_source="inference_service",
        enable_background_recovery=True,
    ).run()


if __name__ == "__main__":
    main()
