# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from typing import Any

from agent_framework import (
    Agent,
    AgentExecutorRequest,
    AgentExecutorResponse,
    Executor,
    Message,
    WorkflowContext,
    handler,
)
from agent_framework.azure import AzureOpenAIResponsesClient
from agent_framework.orchestrations import ConcurrentBuilder
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

"""
Sample: Concurrent Orchestration with Custom Agent Executors

This sample shows a concurrent fan-out/fan-in pattern using child Executor classes
that each own their Agent. The executors accept AgentExecutorRequest inputs
and emit AgentExecutorResponse outputs, which allows reuse of the high-level
ConcurrentBuilder API and the default aggregator.

Demonstrates:
- Executors that create their Agent in __init__ (via AzureOpenAIResponsesClient)
- A @handler that converts AgentExecutorRequest -> AgentExecutorResponse
- ConcurrentBuilder(participants=[...]) to build fan-out/fan-in
- Default aggregator returning list[Message] (one user + one assistant per agent)
- Workflow completion when all participants become idle

Prerequisites:
- AZURE_AI_PROJECT_ENDPOINT must be your Azure AI Foundry Agent Service (V2) project endpoint.
- Azure OpenAI configured for AzureOpenAIResponsesClient with required environment variables.
- Authentication via azure-identity. Use AzureCliCredential and run az login before executing the sample.
"""


class ResearcherExec(Executor):
    agent: Agent

    def __init__(self, client: AzureOpenAIResponsesClient, id: str = "researcher"):
        self.agent = client.as_agent(
            instructions=(
                "You're an expert market and product researcher. Given a prompt, provide concise, factual insights,"
                " opportunities, and risks."
            ),
            name=id,
        )
        super().__init__(id=id)

    @handler
    async def run(self, request: AgentExecutorRequest, ctx: WorkflowContext[AgentExecutorResponse]) -> None:
        response = await self.agent.run(request.messages)
        full_conversation = list(request.messages) + list(response.messages)
        await ctx.send_message(AgentExecutorResponse(self.id, response, full_conversation=full_conversation))


class MarketerExec(Executor):
    agent: Agent

    def __init__(self, client: AzureOpenAIResponsesClient, id: str = "marketer"):
        self.agent = client.as_agent(
            instructions=(
                "You're a creative marketing strategist. Craft compelling value propositions and target messaging"
                " aligned to the prompt."
            ),
            name=id,
        )
        super().__init__(id=id)

    @handler
    async def run(self, request: AgentExecutorRequest, ctx: WorkflowContext[AgentExecutorResponse]) -> None:
        response = await self.agent.run(request.messages)
        full_conversation = list(request.messages) + list(response.messages)
        await ctx.send_message(AgentExecutorResponse(self.id, response, full_conversation=full_conversation))


class LegalExec(Executor):
    agent: Agent

    def __init__(self, client: AzureOpenAIResponsesClient, id: str = "legal"):
        self.agent = client.as_agent(
            instructions=(
                "You're a cautious legal/compliance reviewer. Highlight constraints, disclaimers, and policy concerns"
                " based on the prompt."
            ),
            name=id,
        )
        super().__init__(id=id)

    @handler
    async def run(self, request: AgentExecutorRequest, ctx: WorkflowContext[AgentExecutorResponse]) -> None:
        response = await self.agent.run(request.messages)
        full_conversation = list(request.messages) + list(response.messages)
        await ctx.send_message(AgentExecutorResponse(self.id, response, full_conversation=full_conversation))


async def main() -> None:
    client = AzureOpenAIResponsesClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        deployment_name=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=AzureCliCredential(),
    )

    researcher = ResearcherExec(client)
    marketer = MarketerExec(client)
    legal = LegalExec(client)

    workflow = ConcurrentBuilder(participants=[researcher, marketer, legal]).build()

    events = await workflow.run("We are launching a new budget-friendly electric bike for urban commuters.")
    outputs = events.get_outputs()

    if outputs:
        print("===== Final Aggregated Conversation (messages) =====")
        messages: list[Message] | Any = outputs[0]  # Get the first (and typically only) output
        for i, msg in enumerate(messages, start=1):
            name = msg.author_name if msg.author_name else "user"
            print(f"{'-' * 60}\n\n{i:02d} [{name}]:\n{msg.text}")

    """
    Sample Output:

    ===== Final Aggregated Conversation (messages) =====
    ------------------------------------------------------------

    01 [user]:
    We are launching a new budget-friendly electric bike for urban commuters.
    ------------------------------------------------------------

    02 [researcher]:
    **Insights:**

    - **Target Demographic:** Urban commuters seeking affordable, eco-friendly transport;
        likely to include students, young professionals, and price-sensitive urban residents.
    - **Market Trends:** E-bike sales are growing globally, with increasing urbanization,
        higher fuel costs, and sustainability concerns driving adoption.
    - **Competitive Landscape:** Key competitors include brands like Rad Power Bikes, Aventon,
        Lectric, and domestic budget-focused manufacturers in North America, Europe, and Asia.
    - **Feature Expectations:** Customers expect reliability, ease-of-use, theft protection,
        lightweight design, sufficient battery range for daily city commutes (typically 25-40 miles),
        and low-maintenance components.

    **Opportunities:**

    - **First-time Buyers:** Capture newcomers to e-biking by emphasizing affordability, ease of
        operation, and cost savings vs. public transit/car ownership.
    ...
    ------------------------------------------------------------

    03 [marketer]:
    **Value Proposition:**
    "Empowering your city commute: Our new electric bike combines affordability, reliability, and
        sustainable design—helping you conquer urban journeys without breaking the bank."

    **Target Messaging:**

    *For Young Professionals:*
    ...
    ------------------------------------------------------------

    04 [legal]:
    **Constraints, Disclaimers, & Policy Concerns for Launching a Budget-Friendly Electric Bike for Urban Commuters:**

    **1. Regulatory Compliance**
    - Verify that the electric bike meets all applicable federal, state, and local regulations
        regarding e-bike classification, speed limits, power output, and safety features.
    - Ensure necessary certifications (e.g., UL certification for batteries, CE markings if sold internationally) are obtained.

    **2. Product Safety**
    - Include consumer safety warnings regarding use, battery handling, charging protocols, and age restrictions.
    ...
    """  # noqa: E501


if __name__ == "__main__":
    asyncio.run(main())
