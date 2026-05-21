# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from random import randint
from typing import Annotated

from agent_framework import Agent, tool
from agent_framework.foundry import FoundryChatClient, create_prompt_agent, to_prompt_agent
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv
from pydantic import Field

load_dotenv()

"""
Foundry Prompt Agent Example

This sample demonstrates how a single Agent definition can be both:

1. Run locally via the Foundry Responses API (``agent.run(...)``).
2. Published in one step via ``create_prompt_agent(agent)``, which reuses
   the FoundryChatClient's project client and lifts ``agent_name`` /
   ``description`` from the Agent itself, the recommended path.
3. Published in two steps via ``to_prompt_agent(agent)`` plus
   ``AIProjectClient.agents.create_version(...)`` for when you need a
   standalone definition you can inspect, serialize, or pass to a separately
   managed ``AIProjectClient``.

The model is lifted from the bound ``FoundryChatClient`` so the agent's
``model``/``instructions``/``tools`` stay as the single source of truth.

``to_prompt_agent`` and ``create_prompt_agent`` are experimental
(``ExperimentalFeature.TO_PROMPT_AGENT``) and may change before reaching GA.

Function tools defined in this file are exposed to the prompt agent as
*declarations only*; the deployed agent receives the schema but cannot execute
the local Python. Wire server-side execution separately if you need it.
"""


@tool
def book_hotel(
    city: Annotated[str, Field(description="The city to book the hotel in.")],
    nights: Annotated[int, Field(description="Number of nights to stay.")],
) -> str:
    """Book a hotel room for the given city and number of nights."""
    return f"Booked a hotel in {city} for {nights} nights. Confirmation #CTX-{randint(1000, 9999)}."


async def main() -> None:
    print("=== Foundry Prompt Agent Example ===\n")

    credential = AzureCliCredential()

    agent = Agent(
        client=FoundryChatClient(
            project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            model=os.environ["FOUNDRY_MODEL"],
            credential=credential,
        ),
        # The Agent is the single source of truth for the agent that gets published:
        # `name` becomes the Foundry agent name and `description` becomes the version description.
        # Neither needs to be restated below.
        name="travel-agent",
        description="Helps Contoso employees book travel.",
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

    # 2) Recommended: one-step deploy. `create_prompt_agent` reuses the FoundryChatClient's
    # project client AND lifts `agent_name` / `description` from the Agent itself, so the call
    # site stays minimal. `metadata` and any extra kwargs fall through to
    # AIProjectClient.agents.create_version.
    created = await create_prompt_agent(agent)
    print(f"Prompt agent published via create_prompt_agent: {created.name} v{created.version}")

    # 3) Two-step alternative: use `to_prompt_agent` when you want a standalone definition you
    # can inspect, serialize, or pass to a separately managed AIProjectClient.
    definition = to_prompt_agent(agent)
    project_client = AIProjectClient(
        endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        credential=credential,
    )
    created_v2 = await project_client.agents.create_version(
        agent_name=agent.name,
        definition=definition,
        description=agent.description,
    )
    print(f"Prompt agent published via to_prompt_agent: {created_v2.name} v{created_v2.version}")

    # 4) Cleanup: delete the agent (and all its versions) so re-running the sample stays idempotent.
    await project_client.agents.delete(agent_name=agent.name)
    print(f"Deleted prompt agent {agent.name!r} and all its versions.")


if __name__ == "__main__":
    asyncio.run(main())
