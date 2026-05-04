# Copyright (c) Microsoft. All rights reserved.
import asyncio
import os

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework.orchestrations import SequentialBuilder
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
Sample: Build a sequential workflow orchestration and wrap it as an agent.

The script assembles a sequential conversation flow with `SequentialBuilder`, then
invokes the entire orchestration through the `Agent(client=workflow,...)` interface so
other coordinators can reuse the chain as a single participant.

Note on internal adapters:
- Sequential orchestration includes small adapter nodes for input normalization
  ("input-conversation"), agent-response conversion ("to-conversation:<participant>"),
  and completion ("complete"). These may appear as ExecutorInvoke/Completed events in
  the stream—similar to how concurrent orchestration includes a dispatcher/aggregator.
  You can safely ignore them when focusing on agent progress.

Prerequisites:
- FOUNDRY_PROJECT_ENDPOINT must be set to the Azure Foundry project endpoint.
- FOUNDRY_MODEL must be set to the model name for the Foundry chat client.
"""


async def main() -> None:
    # 1) Create agents
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
        credential=AzureCliCredential(),
    )

    writer = Agent(
        client=client,
        instructions=("You are a concise copywriter. Provide a single, punchy marketing sentence based on the prompt."),
        name="writer",
    )

    reviewer = Agent(
        client=client,
        instructions=("You are a thoughtful reviewer. Give brief feedback on the previous assistant message."),
        name="reviewer",
    )

    # 2) Build sequential workflow: writer -> reviewer
    workflow = SequentialBuilder(participants=[writer, reviewer]).build()

    # 3) Treat the workflow itself as an agent for follow-up invocations
    agent = workflow.as_agent()
    prompt = "Write a tagline for a budget-friendly eBike."
    agent_response = await agent.run(prompt)

    if agent_response.messages:
        print("\n===== Conversation =====")
        for i, msg in enumerate(agent_response.messages, start=1):
            name = msg.author_name or msg.role
            print(f"{'-' * 60}\n{i:02d} [{name}]\n{msg.text}")

    """
    Sample Output:

    ===== Conversation =====
    ------------------------------------------------------------
    01 [reviewer]
    Catchy and straightforward! The tagline clearly emphasizes both the electric aspect and the affordability of the
    eBike. It's inviting and actionable. For even more impact, consider making it slightly shorter:
    "Go electric, save big." Overall, this is an effective and appealing suggestion for a budget-friendly eBike.

    Note:
    `workflow.as_agent()` returns ONLY the final agent's response (the "answer") — the prior agents' work
    is not included in the response. To observe intermediate agents while running as an agent, build with
    `SequentialBuilder(participants=[...], intermediate_outputs=True)`; the intermediate replies are then
    surfaced as `data` events and merged into the AgentResponse.
    """


if __name__ == "__main__":
    asyncio.run(main())
