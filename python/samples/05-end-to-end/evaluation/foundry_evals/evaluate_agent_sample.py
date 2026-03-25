# Copyright (c) Microsoft. All rights reserved.

"""Evaluate an agent using Azure AI Foundry's built-in evaluators.

This sample demonstrates three patterns:
1. evaluate_agent(responses=...) — Evaluate a response you already have.
2. evaluate_agent(queries=...) — Run the agent against test queries and evaluate in one call.
3. FoundryEvals.evaluate() — Full control with direct evaluator access.

Prerequisites:
- An Azure AI Foundry project with a deployed model
- Set FOUNDRY_PROJECT_ENDPOINT and AZURE_AI_MODEL_DEPLOYMENT_NAME in .env
"""

import asyncio
import os

from agent_framework import Agent, AgentEvalConverter, ConversationSplit, evaluate_agent
from agent_framework.foundry import FoundryChatClient
from agent_framework_azure_ai import FoundryEvals
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv

load_dotenv()


# Define a simple tool for the agent
def get_weather(location: str) -> str:
    """Get the current weather for a location."""
    weather_data = {
        "seattle": "62°F, cloudy with a chance of rain",
        "london": "55°F, overcast",
        "paris": "68°F, partly sunny",
    }
    return weather_data.get(location.lower(), f"Weather data not available for {location}")


def get_flight_price(origin: str, destination: str) -> str:
    """Get the price of a flight between two cities."""
    return f"Flights from {origin} to {destination}: $450 round-trip"


async def main() -> None:
    # 1. Set up the Azure AI project client
    project_client = AIProjectClient(
        endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        credential=AzureCliCredential(),
    )

    deployment = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4o")

    # 2. Create an agent with tools
    agent = Agent(
        client=FoundryChatClient(project_client=project_client, model=deployment),
        name="travel-assistant",
        instructions=(
            "You are a helpful travel assistant. Use your tools to answer questions about weather and flights."
        ),
        tools=[get_weather, get_flight_price],
    )

    # 3. Create the evaluator — provider config goes here, once
    evals = FoundryEvals(project_client=project_client, model_deployment=deployment)

    # =========================================================================
    # Pattern 1: evaluate_agent(responses=...) — evaluate a response you already have
    # =========================================================================
    print("=" * 60)
    print("Pattern 1: evaluate_agent(responses=...) — evaluate existing response")
    print("=" * 60)

    query = "How much does a flight from Seattle to Paris cost?"
    response = await agent.run(query)
    print(f"Agent said: {response.text[:100]}...")

    # Pass agent= so tool definitions are extracted, queries= for the eval item context
    results = await evaluate_agent(
        agent=agent,
        responses=response,
        queries=[query],
        evaluators=FoundryEvals(
            project_client=project_client,
            model_deployment=deployment,
            evaluators=[FoundryEvals.RELEVANCE, FoundryEvals.TOOL_CALL_ACCURACY],
        ),
    )

    for r in results:
        print(f"Status: {r.status}")
        print(f"Results: {r.passed}/{r.total} passed")
        print(f"Portal: {r.report_url}")
        if r.all_passed:
            print("✓ All passed")
        else:
            print(f"✗ {r.failed} failed, {r.errored} errored")

    # =========================================================================
    # Pattern 2a: evaluate_agent() — batch test queries
    # =========================================================================
    print()
    print("=" * 60)
    print("Pattern 2a: evaluate_agent()")
    print("=" * 60)

    # Calls agent.run() under the covers for each query, then evaluates
    results = await evaluate_agent(
        agent=agent,
        queries=[
            "What's the weather like in Seattle?",
            "How much does a flight from Seattle to Paris cost?",
            "What should I pack for London?",
        ],
        evaluators=evals,  # uses smart defaults (auto-adds tool_call_accuracy)
    )

    for r in results:
        print(f"Status: {r.status}")
        print(f"Results: {r.passed}/{r.total} passed")
        print(f"Portal: {r.report_url}")
        if r.all_passed:
            print("✓ All passed")
        else:
            print(f"✗ {r.failed} failed, {r.errored} errored")

    # =========================================================================
    # Pattern 2b: evaluate_agent() — with conversation split override
    # =========================================================================
    print()
    print("=" * 60)
    print("Pattern 2b: evaluate_agent() with conversation_split")
    print("=" * 60)

    # conversation_split forces all evaluators to use the same split strategy.
    # FULL evaluates the entire conversation trajectory against the original query.
    results = await evaluate_agent(
        agent=agent,
        queries=[
            "What's the weather like in Seattle?",
            "What should I pack for London?",
        ],
        evaluators=evals,
        conversation_split=ConversationSplit.FULL,  # overrides evaluator defaults
    )

    for r in results:
        print(f"Status: {r.status}")
        print(f"Results: {r.passed}/{r.total} passed")
        print(f"Portal: {r.report_url}")
        if r.all_passed:
            print("✓ All passed")
        else:
            print(f"✗ {r.failed} failed, {r.errored} errored")

    # =========================================================================
    # Pattern 3: FoundryEvals.evaluate() — manual control
    # =========================================================================
    print()
    print("=" * 60)
    print("Pattern 3: FoundryEvals.evaluate() — manual control")
    print("=" * 60)

    queries = [
        "What's the weather in Paris?",
        "Find me a flight from London to Seattle",
    ]

    items = []
    for q in queries:
        response = await agent.run(q)
        print(f"Query: {q}")
        print(f"Response: {response.text[:100]}...")

        item = AgentEvalConverter.to_eval_item(query=q, response=response, agent=agent)
        items.append(item)

        print(f"  Has tools: {item.tools is not None}")
        if item.tools:
            print(f"  Tools: {[t.name for t in item.tools]}")

    # Submit directly to the evaluator
    tool_evals = FoundryEvals(
        project_client=project_client,
        model_deployment=deployment,
        evaluators=[FoundryEvals.RELEVANCE, FoundryEvals.TOOL_CALL_ACCURACY],
    )
    results = await tool_evals.evaluate(items, eval_name="Travel Assistant Eval")

    print(f"\nStatus: {results.status}")
    print(f"Results: {results.passed}/{results.total} passed")
    print(f"Portal: {results.report_url}")


if __name__ == "__main__":
    asyncio.run(main())
