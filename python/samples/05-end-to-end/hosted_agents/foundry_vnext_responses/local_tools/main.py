# Copyright (c) Microsoft. All rights reserved.

import os
from random import randint

from agent_framework import Agent, tool
from agent_framework.foundry import FoundryChatClient, ResponsesHostServer
from azure.ai.agentserver.responses import InMemoryResponseProvider
from azure.identity import AzureCliCredential
from dotenv import load_dotenv
from pydantic import Field
from typing_extensions import Annotated

# Load environment variables from .env file
load_dotenv()


@tool(approval_mode="never_require")
def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


def main():
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
        credential=AzureCliCredential(),
    )

    agent = Agent(
        client=client,
        name="HelloAgent",
        instructions="You are a friendly assistant. Keep your answers brief.",
        tools=[get_weather],
    )

    server = ResponsesHostServer(agent, provider=InMemoryResponseProvider())
    server.run()


if __name__ == "__main__":
    main()
