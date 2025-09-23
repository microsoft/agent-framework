# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Any

from agent_framework import (
    AgentExecutorRequest,
    AgentExecutorResponse,
    ChatAgent,
    ChatMessage,
    ConcurrentBuilder,
    Executor,
    WorkflowContext,
    handler,
)
from agent_framework.azure import AzureChatClient
from azure.identity import AzureCliCredential

"""
Sample: Concurrent Orchestration with Custom Agent Executors

This sample shows a concurrent fan-out/fan-in pattern using child Executor classes
that each own their ChatAgent. The executors accept AgentExecutorRequest inputs
and emit AgentExecutorResponse outputs, which allows reuse of the high-level
ConcurrentBuilder API and the default aggregator.

Demonstrates:
- Executors that create their ChatAgent in __init__ (via AzureChatClient)
- A @handler that converts AgentExecutorRequest -> AgentExecutorResponse
- ConcurrentBuilder().participants([...]) to build fan-out/fan-in
- Default aggregator returning list[ChatMessage] (one user + one assistant per agent)
- Workflow completion when all participants become idle

Prerequisites:
- Azure OpenAI configured for AzureChatClient (az login + required env vars)
"""


class ResearcherExec(Executor):
    agent: ChatAgent

    def __init__(self, chat_client: AzureChatClient, id: str = "researcher"):
        agent = chat_client.create_agent(
            instructions=(
                "You're an expert market and product researcher. Given a prompt, provide concise, factual insights,"
                " opportunities, and risks."
            ),
            name=id,
        )
        super().__init__(agent=agent, id=id)

    @handler
    async def run(self, request: AgentExecutorRequest, ctx: WorkflowContext[AgentExecutorResponse]) -> None:
        response = await self.agent.run(request.messages)
        full_conversation = list(request.messages) + list(response.messages)
        await ctx.send_message(AgentExecutorResponse(self.id, response, full_conversation=full_conversation))


class MarketerExec(Executor):
    agent: ChatAgent

    def __init__(self, chat_client: AzureChatClient, id: str = "marketer"):
        agent = chat_client.create_agent(
            instructions=(
                "You're a creative marketing strategist. Craft compelling value propositions and target messaging"
                " aligned to the prompt."
            ),
            name=id,
        )
        super().__init__(agent=agent, id=id)

    @handler
    async def run(self, request: AgentExecutorRequest, ctx: WorkflowContext[AgentExecutorResponse]) -> None:
        response = await self.agent.run(request.messages)
        full_conversation = list(request.messages) + list(response.messages)
        await ctx.send_message(AgentExecutorResponse(self.id, response, full_conversation=full_conversation))


class LegalExec(Executor):
    agent: ChatAgent

    def __init__(self, chat_client: AzureChatClient, id: str = "legal"):
        agent = chat_client.create_agent(
            instructions=(
                "You're a cautious legal/compliance reviewer. Highlight constraints, disclaimers, and policy concerns"
                " based on the prompt."
            ),
            name=id,
        )
        super().__init__(agent=agent, id=id)

    @handler
    async def run(self, request: AgentExecutorRequest, ctx: WorkflowContext[AgentExecutorResponse]) -> None:
        response = await self.agent.run(request.messages)
        full_conversation = list(request.messages) + list(response.messages)
        await ctx.send_message(AgentExecutorResponse(self.id, response, full_conversation=full_conversation))


async def main() -> None:
    chat_client = AzureChatClient(credential=AzureCliCredential())

    researcher = ResearcherExec(chat_client)
    marketer = MarketerExec(chat_client)
    legal = LegalExec(chat_client)

    workflow = ConcurrentBuilder().participants([researcher, marketer, legal]).build()

    events = await workflow.run("We are launching a new budget-friendly electric bike for urban commuters.")
    outputs = events.get_outputs()

    if outputs:
        print("===== Final Aggregated Conversation (messages) =====")
        messages: list[ChatMessage] | Any = outputs[0]  # Get the first (and typically only) output
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
