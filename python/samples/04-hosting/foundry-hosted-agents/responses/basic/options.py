# Copyright (c) Microsoft. All rights reserved.

"""Map selected Responses request fields to agent run options with a custom input parser."""

import os

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework.openai import OpenAIChatOptions
from agent_framework_foundry_hosting import (
    AgentTurn,
    ResponsesHostServer,
    ResponsesRequest,
    response_input_messages,
)
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()


async def parse_input(request: ResponsesRequest) -> AgentTurn:
    """Forward the caller's temperature; keep the agent's own output-token default."""
    options: OpenAIChatOptions = {}
    temperature = request.request.get("temperature")
    if temperature is not None:
        options["temperature"] = temperature
    return AgentTurn(messages=await response_input_messages(request), options=dict(options))


def main() -> None:
    agent = Agent(
        client=FoundryChatClient(
            project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            model=os.environ.get("FOUNDRY_MODEL") or os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            credential=DefaultAzureCredential(),
        ),
        instructions="Be concise.",
        default_options=OpenAIChatOptions(max_tokens=256),
    )
    ResponsesHostServer(
        agent=agent,
        history_source="host_managed",
        parse_input=parse_input,
    ).run()


if __name__ == "__main__":
    main()
