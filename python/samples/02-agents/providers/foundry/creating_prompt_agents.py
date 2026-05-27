# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from random import randint
from typing import Annotated

from agent_framework import Agent, tool
from agent_framework.foundry import FoundryChatClient, to_prompt_agent
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv
from pydantic import Field

load_dotenv()

"""
Foundry Prompt Agent Example

This sample demonstrates how a single Agent definition can be both:

1. Run locally via the Foundry Responses API (``agent.run(...)``).
2. Converted to a ``PromptAgentDefinition`` with ``to_prompt_agent(agent)`` and
   published via ``AIProjectClient.agents.create_version(...)``.

The model is lifted from the bound ``FoundryChatClient`` and every generation
parameter that has an Agent Framework equivalent (``temperature``, ``top_p``,
``tool_choice``, ``reasoning``, ``response_format`` / ``text`` / ``verbosity``)
is sourced from the agent's ``default_options``, so the ``Agent`` is the
single source of truth for them.

Only Foundry-only fields (``structured_inputs``, ``rai_config``) are exposed
as keyword arguments on ``to_prompt_agent``.

``to_prompt_agent`` is experimental
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
    project_client = AIProjectClient(endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"], credential=credential)

    agent = Agent(
        client=FoundryChatClient(
            project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            model=os.environ["FOUNDRY_MODEL"],
            credential=credential,
        ),
        # The Agent is the single source of truth for the agent that gets published:
        # `name` becomes the Foundry agent name and `description` becomes the version description.
        name="travel-agent",
        description="Helps Contoso employees book travel.",
        instructions="You are a helpful travel assistant. Use the booking tool when asked.",
        tools=[
            FoundryChatClient.get_web_search_tool(),
            FoundryChatClient.get_code_interpreter_tool(),
            book_hotel,
        ],
        # Generation parameters set on the Agent flow through to the published prompt agent.
        default_options={
            "temperature": 0.3,
            "top_p": 0.95,
            "reasoning": {"effort": "medium"},
        },
    )

    # 1) Run locally via the Foundry Responses API
    local_query = "Book me a hotel in Seattle for 3 nights."
    print(f"User (local run): {local_query}")
    response = await agent.run(local_query)
    print(f"Agent: {response}\n")

    # 2) Convert and publish. `to_prompt_agent` lifts `model`, `instructions`, `tools`, and every
    # generation parameter from `default_options`. Use kwargs only for Foundry-only fields
    # (`structured_inputs`, `rai_config`) that have no Agent Framework equivalent.
    definition = to_prompt_agent(agent)
    created = await project_client.agents.create_version(
        agent_name=agent.name,
        definition=definition,
        description=agent.description,
    )
    print(f"Prompt agent published: {created.name} v{created.version}")

    # 3) Cleanup: delete the agent (and all its versions) so re-running the sample stays idempotent.
    await project_client.agents.delete(agent_name=agent.name)
    print(f"Deleted prompt agent {agent.name!r} and all its versions.")


if __name__ == "__main__":
    asyncio.run(main())
