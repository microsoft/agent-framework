# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework import Agent, AgentResponseUpdate
from agent_framework.foundry import FoundryChatClient
from agent_framework.orchestrations import SequentialBuilder
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

"""
Sample: Sequential workflow with chain_only_agent_responses=True

Demonstrates SequentialBuilder with `chain_only_agent_responses=True`, which passes
only the previous agent's response (not the full conversation history) to the next
agent. This is useful when each agent should focus solely on refining or transforming
the prior agent's output without being influenced by earlier turns.

In this sample, a writer agent produces a draft tagline, a translator agent translates
it into French (seeing only the writer's output, not the original user prompt), and a
reviewer agent evaluates the translation (seeing only the translator's output).

Compare with `sequential_agents.py`, which uses the default behavior where the full
conversation context is passed to each agent.

Prerequisites:
- FOUNDRY_PROJECT_ENDPOINT must be your Azure AI Foundry Agent Service (V2) project endpoint.
- FOUNDRY_MODEL must be the deployment name of a model in your Foundry project.
- Authentication via azure-identity. Use AzureCliCredential and run az login before executing the sample.
"""

# Load environment variables from .env file
load_dotenv()


async def main() -> None:
    # 1) Create agents
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
        credential=AzureCliCredential(),
    )

    writer = Agent(
        client=client,
        instructions="You are a concise copywriter. Provide a single, punchy marketing sentence based on the prompt.",
        name="writer",
    )

    translator = Agent(
        client=client,
        instructions="You are a translator. Translate the given text into French. Output only the translation.",
        name="translator",
    )

    reviewer = Agent(
        client=client,
        instructions="You are a reviewer. Evaluate the quality of the marketing tagline.",
        name="reviewer",
    )

    # 2) Build sequential workflow: writer -> translator -> reviewer
    #    chain_only_agent_responses=True means each agent sees only the previous agent's reply,
    #    not the full conversation history.
    workflow = SequentialBuilder(
        participants=[writer, translator, reviewer],
        chain_only_agent_responses=True,
        intermediate_outputs=True,
    ).build()

    # 3) Run and collect outputs
    last_agent: str | None = None
    async for event in workflow.run("Write a tagline for a budget-friendly eBike.", stream=True):
        if event.type == "output" and isinstance(event.data, AgentResponseUpdate):
            if event.data.author_name != last_agent:
                last_agent = event.data.author_name
                print()
                print(f"{last_agent}: ", end="", flush=True)
            print(event.data.text, end="", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
