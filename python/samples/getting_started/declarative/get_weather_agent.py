# Copyright (c) Microsoft. All rights reserved.
import asyncio
from pathlib import Path
from random import randint
from typing import Literal

from agent_framework.azure import AzureOpenAIResponsesClient
from agent_framework.declarative import AgentFactory
from azure.identity import AzureCliCredential


def get_weather(location: str, unit: Literal["celsius", "fahrenheit"] = "celsius") -> str:
    """A simple function tool to get weather information."""
    return f"The weather in {location} is {randint(-10, 30) if unit == 'celsius' else randint(30, 100)} degrees {unit}."


async def main():
    """Create an agent from a declarative yaml specification and run it."""
    # get the path
    current_path = Path(__file__).parent
    yaml_path = current_path.parent.parent.parent.parent / "agent-samples" / "chatclient" / "GetWeather.yaml"

    # load the yaml from the path
    with yaml_path.open("r") as f:
        yaml_str = f.read()

    # create the AgentFactory with a chat client and bindings
    agent_factory = AgentFactory(
        chat_client=AzureOpenAIResponsesClient(credential=AzureCliCredential()),
        bindings={"get_weather": get_weather},
    )
    # create the agent from the yaml
    agent = agent_factory.create_agent_from_yaml(yaml_str)
    # use the agent
    response = await agent.run("What's the weather in Amsterdam, in celsius?")
    print("Agent response:", response.text)


if __name__ == "__main__":
    asyncio.run(main())
