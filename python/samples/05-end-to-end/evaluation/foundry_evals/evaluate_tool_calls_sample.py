# Copyright (c) Microsoft. All rights reserved.

"""Evaluate tool-calling accuracy using Azure AI Foundry's TOOL_CALL_ACCURACY evaluator.

This sample demonstrates evaluating how well an agent selects and invokes tools
by using ``FoundryEvals.evaluate()`` with ``TOOL_CALL_ACCURACY``.

Prerequisites:
- An Azure AI Foundry project with a deployed model
- Set FOUNDRY_PROJECT_ENDPOINT and AZURE_AI_MODEL_DEPLOYMENT_NAME in .env
"""

import asyncio
import os

from agent_framework import Agent, AgentEvalConverter
from agent_framework.foundry import FoundryChatClient, FoundryEvals
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import AzureCliCredential
from dotenv import load_dotenv

load_dotenv()


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
    project_client = AIProjectClient(
        endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        credential=AzureCliCredential(),
    )

    deployment = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4o")
    chat_client = FoundryChatClient(project_client=project_client, model=deployment)

    # Create an agent with tools
    agent = Agent(
        client=chat_client,
        name="travel-assistant",
        instructions=(
            "You are a helpful travel assistant. "
            "Use your tools to answer questions about weather and flights."
        ),
        tools=[get_weather, get_flight_price],
    )

    # Run the agent and convert responses to eval items
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

    # Submit to Foundry with tool_call_accuracy evaluator
    evals = FoundryEvals(
        client=chat_client,
        model=deployment,
        evaluators=[FoundryEvals.RELEVANCE, FoundryEvals.TOOL_CALL_ACCURACY],
    )
    results = await evals.evaluate(items, eval_name="Tool Call Accuracy Eval")

    print(f"\nStatus: {results.status}")
    print(f"Results: {results.passed}/{results.total} passed")
    print(f"Portal: {results.report_url}")


if __name__ == "__main__":
    asyncio.run(main())
