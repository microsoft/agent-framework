# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import ConcurrentBuilder
from agent_framework.azure import AzureOpenAIChatClient
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
- Azure OpenAI access configured for AzureOpenAIChatClient (use az login + env vars)
- Familiarity with Workflow events (AgentRunEvent, WorkflowOutputEvent)
"""


async def main() -> None:
    # 1) Create three domain agents using AzureOpenAIChatClient
    chat_client = AzureOpenAIChatClient(credential=AzureCliCredential())

    researcher = chat_client.create_agent(
        instructions=(
            "You're an expert market and product researcher. Given a prompt, provide concise, factual insights,"
            " opportunities, and risks."
        ),
        name="researcher",
    )

    marketer = chat_client.create_agent(
        instructions=(
            "You're a creative marketing strategist. Craft compelling value propositions and target messaging"
            " aligned to the prompt."
        ),
        name="marketer",
    )

    legal = chat_client.create_agent(
        instructions=(
            "You're a cautious legal/compliance reviewer. Highlight constraints, disclaimers, and policy concerns"
            " based on the prompt."
        ),
        name="legal",
    )

    # 2) Build a concurrent workflow
    workflow = ConcurrentBuilder().participants([researcher, marketer, legal]).build()

    # 3) Expose the concurrent workflow as an agent for easy reuse
    agent = workflow.as_agent(name="ConcurrentWorkflowAgent")
    prompt = "We are launching a new budget-friendly electric bike for urban commuters."
    agent_response = await agent.run(prompt)

    if agent_response.messages:
        print("\n===== Aggregated Messages =====")
        for i, msg in enumerate(agent_response.messages, start=1):
            role = getattr(msg.role, "value", msg.role)
            name = msg.author_name if msg.author_name else role
            print(f"{'-' * 60}\n\n{i:02d} [{name}]:\n{msg.text}")

    """
    Sample Output:

    ===== Aggregated Messages =====
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
