# Copyright (c) Microsoft. All rights reserved.

"""Evaluate an agent using Azure AI Foundry's built-in evaluators.

This sample demonstrates two patterns:
1. evaluate_agent(responses=...) — Evaluate a response you already have.
2. evaluate_agent(queries=...) — Run the agent against test queries and evaluate in one call.

See ``evaluate_tool_calls_sample.py`` for tool-call accuracy evaluation.

Prerequisites:
- An Azure AI Foundry project with a deployed model
- Set FOUNDRY_PROJECT_ENDPOINT and AZURE_AI_MODEL_DEPLOYMENT_NAME in .env
"""

import asyncio
import os

from agent_framework import Agent, ConversationSplit, evaluate_agent
from agent_framework.foundry import FoundryChatClient, FoundryEvals
from azure.identity import AzureCliCredential
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
    # 1. Set up the FoundryChatClient
    chat_client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ.get("FOUNDRY_MODEL", "gpt-4o"),
        credential=AzureCliCredential(),
    )

    # 2. Create an agent with tools
    agent = Agent(
        client=chat_client,
        name="travel-assistant",
        instructions=(
            "You are a helpful travel assistant. Use your tools to answer questions about weather and flights."
        ),
        tools=[get_weather, get_flight_price],
    )

    # 3. Create the evaluator — provider config goes here, once
    evals = FoundryEvals(client=chat_client)

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
            client=chat_client,
            evaluators=[FoundryEvals.RELEVANCE, FoundryEvals.TOOL_CALL_ACCURACY],
        ),
    )

    for r in results:
        print(f"Status: {r.status}")
        print(f"Results: {r.passed}/{r.total} passed")
        print(f"Portal: {r.report_url}")
        if r.all_passed:
            print("[PASS] All passed")
        else:
            print(f"[FAIL] {r.failed} failed")

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
            print("[PASS] All passed")
        else:
            print(f"[FAIL] {r.failed} failed")

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
            print("[PASS] All passed")
        else:
            print(f"[FAIL] {r.failed} failed")


if __name__ == "__main__":
    asyncio.run(main())
