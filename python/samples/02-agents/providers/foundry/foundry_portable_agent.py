# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from random import randint
from typing import Annotated

from agent_framework import Agent, tool
from agent_framework.foundry import FoundryChatClient, to_prompt_agent
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv
from pydantic import Field

load_dotenv()

"""
Foundry Portable Agent Example

This sample demonstrates how a single Agent definition can be both:

1. Run locally via the Foundry Responses API (``agent.run(...)``), and
2. Published as a Foundry prompt agent (``to_prompt_agent(agent)`` + ``AIProjectClient.agents.create_version(...)``)

The model is lifted from the bound ``FoundryChatClient`` so the agent's
``model``/``instructions``/``tools`` stay as the single source of truth.

``to_prompt_agent`` is experimental (``ExperimentalFeature.TO_PROMPT_AGENT``)
and may change before reaching GA.

Function tools defined in this file are exposed to the prompt agent as
*declarations only*; the deployed agent receives the schema but cannot execute
the local Python. Wire server-side execution separately if you need it.
"""


# NOTE: approval_mode="never_require" is for sample brevity. Use "always_require" in production;
# see samples/02-agents/tools/function_tool_with_approval.py.
@tool(approval_mode="never_require")
def book_hotel(
    city: Annotated[str, Field(description="The city to book the hotel in.")],
    nights: Annotated[int, Field(description="Number of nights to stay.")],
) -> str:
    """Book a hotel room for the given city and number of nights."""
    return f"Booked a hotel in {city} for {nights} nights. Confirmation #CTX-{randint(1000, 9999)}."


async def main() -> None:
    print("=== Foundry Portable Agent Example ===\n")

    async with AzureCliCredential() as credential:
        client = FoundryChatClient(
            project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            model=os.environ["FOUNDRY_MODEL"],
            credential=credential,
        )

        agent = Agent(
            client=client,
            name="TravelAgent",
            instructions="You are a helpful travel assistant. Use the booking tool when asked.",
            tools=[
                FoundryChatClient.get_web_search_tool(),
                FoundryChatClient.get_code_interpreter_tool(),
                book_hotel,
            ],
        )

        # 1) Run locally via the Foundry Responses API
        local_query = "Book me a hotel in Seattle for 3 nights."
        print(f"User (local run): {local_query}")
        response = await agent.run(local_query)
        print(f"Agent: {response}\n")

        # 2) Publish the same definition as a Foundry prompt agent
        definition = to_prompt_agent(agent)
        print("PromptAgentDefinition (would be sent to AIProjectClient.agents.create_version):")
        print(definition.as_dict())

        # Uncomment to actually publish the prompt agent to your Foundry project:
        # from azure.ai.projects.aio import AIProjectClient
        #
        # async with AIProjectClient(
        #     endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        #     credential=credential,
        # ) as project_client:
        #     created = await project_client.agents.create_version(
        #         name="travel-agent",
        #         definition=definition,
        #     )
        #     print(f"Prompt agent published: {created.name} v{created.version}")


if __name__ == "__main__":
    asyncio.run(main())
