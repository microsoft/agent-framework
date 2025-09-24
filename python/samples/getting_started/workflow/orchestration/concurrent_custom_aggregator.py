# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Any

from agent_framework import ChatMessage, ConcurrentBuilder, Role
from agent_framework.azure import AzureChatClient
from azure.identity import AzureCliCredential

"""
Sample: Concurrent Orchestration with Custom Aggregator

Build a concurrent workflow with ConcurrentBuilder that fans out one prompt to
multiple domain agents and fans in their responses. Override the default
aggregator with a custom async callback that uses AzureChatClient.get_response()
to synthesize a concise, consolidated summary from the experts' outputs.
The workflow completes when all participants become idle.

Demonstrates:
- ConcurrentBuilder().participants([...]).with_custom_aggregator(callback)
- Fan-out to agents and fan-in at an aggregator
- Aggregation implemented via an LLM call (chat_client.get_response)
- Workflow output yielded with the synthesized summary string

Prerequisites:
- Azure OpenAI configured for AzureChatClient (az login + required env vars)
"""


async def main() -> None:
    chat_client = AzureChatClient(credential=AzureCliCredential())

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

    # Define a custom aggregator callback that uses the chat client to summarize
    async def summarize_results(results: list[Any]) -> str:
        # Extract one final assistant message per agent
        expert_sections: list[str] = []
        for r in results:
            try:
                messages = getattr(r.agent_run_response, "messages", [])
                final_text = messages[-1].text if messages and hasattr(messages[-1], "text") else "(no content)"
                expert_sections.append(f"{getattr(r, 'executor_id', 'expert')}:\n{final_text}")
            except Exception as e:
                expert_sections.append(f"{getattr(r, 'executor_id', 'expert')}: (error: {type(e).__name__}: {e})")

        # Ask the model to synthesize a concise summary of the experts' outputs
        system_msg = ChatMessage(
            Role.SYSTEM,
            text=(
                "You are a helpful assistant that consolidates multiple domain expert outputs "
                "into one cohesive, concise summary with clear takeaways. Keep it under 200 words."
            ),
        )
        user_msg = ChatMessage(Role.USER, text="\n\n".join(expert_sections))

        response = await chat_client.get_response([system_msg, user_msg])
        # Return the model's final assistant text as the completion result
        return response.messages[-1].text if response.messages else ""

    # Build with a custom aggregator callback function
    # - participants([...]) accepts AgentProtocol (agents) or Executor instances.
    #   Each participant becomes a parallel branch (fan-out) from an internal dispatcher.
    # - with_aggregator(...) overrides the default aggregator:
    #   • Default aggregator -> returns list[ChatMessage] (one user + one assistant per agent)
    #   • Custom callback    -> return value becomes workflow output (string here)
    #   The callback can be sync or async; it receives list[AgentExecutorResponse].
    workflow = (
        ConcurrentBuilder().participants([researcher, marketer, legal]).with_aggregator(summarize_results).build()
    )

    events = await workflow.run("We are launching a new budget-friendly electric bike for urban commuters.")
    outputs = events.get_outputs()

    if outputs:
        print("===== Final Consolidated Output =====")
        print(outputs[0])  # Get the first (and typically only) output

    """
    Sample Output:

    ===== Final Consolidated Output =====
    Urban e-bike demand is rising rapidly due to eco-awareness, urban congestion, and high fuel costs,
    with market growth projected at a ~10% CAGR through 2030. Key customer concerns are affordability,
    easy maintenance, convenient charging, compact design, and theft protection. Differentiation opportunities
    include integrating smart features (GPS, app connectivity), offering subscription or leasing options, and
    developing portable, space-saving designs. Partnering with local governments and bike shops can boost visibility.

    Risks include price wars eroding margins, regulatory hurdles, battery quality concerns, and heightened expectations
    for after-sales support. Accurate, substantiated product claims and transparent marketing (with range disclaimers)
    are essential. All e-bikes must comply with local and federal regulations on speed, wattage, safety certification,
    and labeling. Clear warranty, safety instructions (especially regarding batteries), and inclusive, accessible
    marketing are required. For connected features, data privacy policies and user consents are mandatory.

    Effective messaging should target young professionals, students, eco-conscious commuters, and first-time buyers,
    emphasizing affordability, convenience, and sustainability. Slogan suggestion: “Charge Ahead—City Commutes Made
    Affordable.” Legal review in each target market, compliance vetting, and robust customer support policies are
    critical before launch.
    """


if __name__ == "__main__":
    asyncio.run(main())
