# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework.azure import AzureOpenAIResponsesClient
from agent_framework.orchestrations import ConcurrentBuilder
from azure.identity import AzureCliCredential

"""
Sample: Build a concurrent workflow orchestration and wrap it as an agent.

This script wires up a fan-out/fan-in workflow using `ConcurrentBuilder`, and then
invokes the entire orchestration through the `workflow.as_agent(...)` interface so
downstream coordinators can reuse the orchestration as a single agent.

Demonstrates:
- Fan-out to multiple agents, fan-in aggregation of final ChatMessages.
- Reusing the orchestrated workflow as an agent entry point with `workflow.as_agent(...)`.
- Workflow completion when idle with no pending work

Prerequisites:
- AZURE_AI_PROJECT_ENDPOINT must be your Azure AI Foundry Agent Service (V2) project endpoint.
- Azure OpenAI access configured for AzureOpenAIResponsesClient (use az login + env vars)
- Familiarity with Workflow events (WorkflowEvent with type "output")
"""


async def main() -> None:
    # 1) Create three domain agents using AzureOpenAIResponsesClient
    client = AzureOpenAIResponsesClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        deployment_name=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=AzureCliCredential(),
    )

    researcher = client.as_agent(
        instructions=(
            "You're an expert market and product researcher. Given a prompt, provide concise, factual insights,"
            " opportunities, and risks."
        ),
        name="researcher",
    )

    marketer = client.as_agent(
        instructions=(
            "You're a creative marketing strategist. Craft compelling value propositions and target messaging"
            " aligned to the prompt."
        ),
        name="marketer",
    )

    legal = client.as_agent(
        instructions=(
            "You're a cautious legal/compliance reviewer. Highlight constraints, disclaimers, and policy concerns"
            " based on the prompt."
        ),
        name="legal",
    )

    # 2) Build a concurrent workflow
    workflow = ConcurrentBuilder(participants=[researcher, marketer, legal]).build()

    # 3) Expose the concurrent workflow as an agent for easy reuse
    agent = workflow.as_agent(name="ConcurrentWorkflowAgent")
    prompt = "We are launching a new budget-friendly electric bike for urban commuters."

    agent_response = await agent.run(prompt)
    print("===== Final Aggregated Response =====\n")
    for message in agent_response.messages:
        # The agent_response contains messages from all participants concatenated
        # into a single message.
        print(f"{message.author_name}: {message.text}\n")


if __name__ == "__main__":
    asyncio.run(main())
