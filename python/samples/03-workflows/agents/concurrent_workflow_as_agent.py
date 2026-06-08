# Copyright (c) Microsoft. All rights reserved.
import asyncio
import os

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework.orchestrations import ConcurrentBuilder
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
Sample: Build a concurrent workflow orchestration and wrap it as an agent.

This script wires up a fan-out/fan-in workflow using `ConcurrentBuilder`, and then
invokes the entire orchestration through the `Agent(client=workflow,...)` interface so
downstream coordinators can reuse the orchestration as a single agent.

Demonstrates:
- Fan-out to multiple agents, fan-in aggregation of final ChatMessages.
- Reusing the orchestrated workflow as an agent entry point with `Agent(client=workflow,...)`.
- Workflow completion when idle with no pending work

Prerequisites:
- FOUNDRY_PROJECT_ENDPOINT must be your Azure AI Foundry Agent Service (V2) project endpoint.
- FOUNDRY_MODEL must be set to your Azure OpenAI model deployment name.
- Familiarity with Workflow events (WorkflowEvent with type "output")
"""


async def main() -> None:
    # 1) Create three domain agents using FoundryChatClient
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
        credential=AzureCliCredential(),
    )

    researcher = Agent(
        client=client,
        instructions=(
            "You're an expert market and product researcher. Given a prompt, provide concise, factual insights,"
            " opportunities, and risks."
        ),
        name="researcher",
    )

    marketer = Agent(
        client=client,
        instructions=(
            "You're a creative marketing strategist. Craft compelling value propositions and target messaging"
            " aligned to the prompt."
        ),
        name="marketer",
    )

    legal = Agent(
        client=client,
        instructions=(
            "You're a cautious legal/compliance reviewer. Highlight constraints, disclaimers, and policy concerns"
            " based on the prompt."
        ),
        name="legal",
    )

    # 2) Build a concurrent workflow
    workflow = ConcurrentBuilder(participants=[researcher, marketer, legal]).build()

    # 3) Expose the concurrent workflow as an agent for easy reuse
    agent = workflow.as_agent()
    prompt = "We are launching a new budget-friendly electric bike for urban commuters."

    agent_response = await agent.run(prompt)
    print("===== Final Aggregated Response =====\n")
    for message in agent_response.messages:
        # The agent_response contains messages from all participants concatenated
        # into a single message.
        print(f"{message.author_name}: {message.text}\n")


if __name__ == "__main__":
    asyncio.run(main())
