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
2. Run the local ``Agent`` directly against the Foundry Responses API.
3. Convert it with ``to_prompt_agent(agent)`` and publish via
   ``AIProjectClient.agents.create_version(...)``.
4. Connect to the deployed prompt agent with ``FoundryAgent`` and pass the
   *same* ``book_hotel`` callable through ``tools=`` so the server-side prompt
   agent and the client share a single tool definition.

The Foundry prompt agent only receives the ``book_hotel`` *declaration* (its
JSON schema). When the deployed agent decides to call the tool, ``FoundryAgent``
executes the local Python implementation by matching tool names — keeping the
schema on the server and the implementation on the client in sync.

Local ``Agent`` vs deployed prompt agent — compare & contrast when calling
``run`` on each:

* **Runtime / latency.** ``Agent.run`` issues a single ``responses.create``
  call against the Foundry Responses API. ``FoundryAgent.run`` against a
  published prompt agent goes through the Foundry Agents service, which
  resolves the stored ``PromptAgentDefinition`` (instructions, tools,
  generation parameters, RAI config) on every call before forwarding to the
  model. Expect a small per-call overhead on the deployed path in exchange
  for centrally managed configuration.
* **Configurability.** With the local ``Agent``, model, instructions, tools,
  ``default_options``, etc. live in your process — change them, restart, and
  the next ``run`` picks them up. With the deployed prompt agent, those same
  fields are versioned server-side: publishing a new version updates every
  consumer at once and you keep an audit trail of previous versions, but you
  must call ``create_version`` (or pin ``agent_version``) to roll changes
  out or back.
* **Persistence / sharing.** A local ``Agent`` instance only exists for the
  lifetime of the process that created it; tools and instructions are not
  discoverable by anything else. A published prompt agent is a first-class
  Foundry resource — other services, other languages, and the Foundry portal
  can all bind to it by ``agent_name`` (+ optional ``agent_version``) and get
  the same behaviour. Local ``@tool`` callables stay on the client; only
  their JSON schema is persisted, so the implementation must be supplied
  again at connection time via ``FoundryAgent(tools=[...])``.

``to_prompt_agent`` is experimental
(``ExperimentalFeature.TO_PROMPT_AGENT``) and may change before being released.
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

    # Use ``async with`` so the credential and project client are closed even if the
    # body below raises. The ``try/finally`` around ``delete`` further guarantees we
    # don't leave an orphaned prompt agent in the Foundry project after a failure.
    async with (
        AzureCliCredential() as credential,
        AIProjectClient(endpoint=project_endpoint, credential=credential) as project_client,
    ):
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
            default_options={"reasoning": {"effort": "medium"}},
        )

        query = "Book me a hotel in Seattle for 3 nights."

        # 2) Run the local Agent. This calls the Foundry Responses API directly — instructions,
        # tools, and generation parameters live in this process only.
        print(f"User (local Agent):     {query}")
        local_result = await agent.run(query)
        print(f"Local Agent:            {local_result}\n")

        # 3) Convert and publish. The version returned by Foundry includes the version label
        # we need when connecting back to that specific deployment.
        if agent.name is None:
            raise ValueError("Agent name is required to create a prompt agent version.")
        created = await project_client.agents.create_version(
            agent_name=agent.name,
            # note this line:
            definition=to_prompt_agent(agent),
            description=agent.description,
        )
        print(f"Published prompt agent: {created.name} v{created.version}\n")

        try:
            # 4) Connect to the deployed prompt agent with FoundryAgent and pass the *same* callable
            # tool. FoundryAgent runs the local function when the server-side agent invokes the tool,
            # matching by name. Compared to step 2, instructions/tools/generation parameters now
            # come from the stored PromptAgentDefinition rather than this process.
            deployed = FoundryAgent(
                project_endpoint=project_endpoint,
                agent_name=created.name,
                agent_version=created.version,
                credential=credential,
                tools=[book_hotel],
            )

            print(f"User (deployed agent):  {query}")
            deployed_result = await deployed.run(query)
            print(f"Deployed Agent:         {deployed_result}")
        finally:
            # 5) Cleanup: delete the deployed prompt agent (and all its versions) even if step 4
            # raised, so re-running the sample stays idempotent and we don't leak resources in
            # the Foundry project.
            await project_client.agents.delete(agent_name=created.name)
            print(f"\nDeleted prompt agent {created.name!r} and all its versions.")


if __name__ == "__main__":
    asyncio.run(main())
