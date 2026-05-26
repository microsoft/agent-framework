# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from random import randint
from typing import Annotated

from agent_framework import Agent, tool
from agent_framework.foundry import FoundryAgent, FoundryChatClient, to_prompt_agent
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv
from pydantic import Field

load_dotenv()

"""
Foundry Prompt Agent: Convert, Publish, Connect, and Run

This sample shows the end-to-end loop:

1. Build an ``Agent`` backed by ``FoundryChatClient`` with a local ``@tool``
   function and Foundry-hosted tools.
2. Convert it with ``to_prompt_agent(agent)`` and publish via
   ``AIProjectClient.agents.create_version(...)``.
3. Connect to the deployed prompt agent with ``FoundryAgent`` and pass the
   *same* ``book_hotel`` callable through ``tools=`` so the server-side prompt
   agent and the client share a single tool definition.

The Foundry prompt agent only receives the ``book_hotel`` *declaration* (its
JSON schema). When the deployed agent decides to call the tool, ``FoundryAgent``
executes the local Python implementation by matching tool names \u2014 keeping the
schema on the server and the implementation on the client in sync.

``to_prompt_agent`` is experimental
(``ExperimentalFeature.TO_PROMPT_AGENT``) and may change before reaching GA.
"""


@tool
def book_hotel(
    city: Annotated[str, Field(description="The city to book the hotel in.")],
    nights: Annotated[int, Field(description="Number of nights to stay.")],
) -> str:
    """Book a hotel room for the given city and number of nights."""
    return f"Booked a hotel in {city} for {nights} nights. Confirmation #CTX-{randint(1000, 9999)}."


async def main() -> None:
    print("=== Foundry Prompt Agent: Convert, Publish, Connect, and Run ===\n")

    project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    model = os.environ["FOUNDRY_MODEL"]
    credential = AzureCliCredential()
    project_client = AIProjectClient(endpoint=project_endpoint, credential=credential)

    # 1) Define the Agent. `name` / `description` set here become the Foundry agent identity
    # on publish; `book_hotel` is the local implementation that backs the published declaration.
    agent = Agent(
        client=FoundryChatClient(
            project_endpoint=project_endpoint,
            model=model,
            credential=credential,
        ),
        name="travel-agent",
        description="Helps Contoso employees book travel.",
        instructions="You are a helpful travel assistant. Use the booking tool when asked.",
        tools=[
            FoundryChatClient.get_web_search_tool(),
            book_hotel,
        ],
        default_options={"temperature": 0.3},
    )

    # 2) Convert and publish. The version returned by Foundry includes the version label
    # we need when connecting back to that specific deployment.
    definition = to_prompt_agent(agent)
    created = await project_client.agents.create_version(
        agent_name=agent.name,
        definition=definition,
        description=agent.description,
    )
    print(f"Published prompt agent: {created.name} v{created.version}\n")

    # 3) Connect to the deployed prompt agent with FoundryAgent and pass the *same* callable.
    # FoundryAgent runs the local function when the server-side agent invokes the tool,
    # matching by name.
    deployed = FoundryAgent(
        project_endpoint=project_endpoint,
        agent_name=created.name,
        agent_version=created.version,
        credential=credential,
        tools=[book_hotel],
    )

    query = "Book me a hotel in Seattle for 3 nights."
    print(f"User: {query}")
    result = await deployed.run(query)
    print(f"Agent: {result}")

    # 4) Cleanup: delete the deployed prompt agent (and all its versions) so re-running the
    # sample stays idempotent.
    await project_client.agents.delete(agent_name=created.name)
    print(f"\nDeleted prompt agent {created.name!r} and all its versions.")


if __name__ == "__main__":
    asyncio.run(main())
