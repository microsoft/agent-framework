# Copyright (c) Microsoft. All rights reserved.

"""Let a developer option hook override a caller's model-option selection."""

import os
from typing import Any

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework.openai import OpenAIChatOptions
from agent_framework_foundry_hosting import HostedResponseRequest, ResponsesHostServer
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()


def prepare_options(_request: HostedResponseRequest, options: dict[str, Any]) -> dict[str, Any]:
    """Use the agent's output-token default instead of the caller's override."""
    options.pop("max_tokens", None)
    return options


def main() -> None:
    agent = Agent(
        client=FoundryChatClient(
            project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            credential=DefaultAzureCredential(),
        ),
        instructions="Be concise.",
        default_options=OpenAIChatOptions(max_tokens=256),
    )
    ResponsesHostServer(
        agent=agent,
        inner_history="host",
        prepare_options=prepare_options,
        unsupported_options="warn",
    ).run()


if __name__ == "__main__":
    main()
