# Copyright (c) Microsoft. All rights reserved.

"""Evaluate a multi-agent workflow using Azure AI Foundry evaluators.

This sample demonstrates two patterns:
1. Post-hoc: Run the workflow, then evaluate the result you already have.
2. Run + evaluate: Pass queries and let evaluate_workflow() run the workflow for you.

Both patterns return a list of results (one per provider), each with a per-agent
breakdown in sub_results so you can identify which agent is underperforming.

Prerequisites:
- An Azure AI Foundry project with a deployed model
- Set FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_MODEL in .env
"""

import asyncio
import os

from agent_framework import Agent, evaluate_workflow
from agent_framework.foundry import FoundryChatClient, FoundryEvals
from agent_framework_orchestrations import SequentialBuilder
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

load_dotenv()


# Simple tools for the agents
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
    # 1. Set up the chat client
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ.get("FOUNDRY_MODEL", "gpt-4o"),
        credential=AzureCliCredential(),
    )

    # 2. Create agents for a sequential workflow
    # Use store=False so agents don't chain conversation state via previous_response_id.
    # This allows the workflow to be run multiple times without stale state issues.
    researcher = Agent(
        client=client,
        name="researcher",
        instructions=(
            "You are a travel researcher. Use your tools to gather weather "
            "and flight information for the destination the user asks about."
        ),
        tools=[get_weather, get_flight_price],
        default_options={"store": False},
    )

    planner = Agent(
        client=client,
        name="planner",
        instructions=(
            "You are a travel planner. Based on the research provided, "
            "create a concise travel recommendation with packing tips."
        ),
        default_options={"store": False},
    )

    # 3. Build a sequential workflow: researcher -> planner
    workflow = SequentialBuilder(participants=[researcher, planner]).build()

    # 4. Create the evaluator — provider config goes here, once
    evals = FoundryEvals(client=client)

    # =========================================================================
    # Pattern 1: Post-hoc — evaluate a workflow run you already did
    # =========================================================================
    print("=" * 60)
    print("Pattern 1: Post-hoc workflow evaluation")
    print("=" * 60)

    result = await workflow.run("Plan a trip from Seattle to Paris")

    eval_results = await evaluate_workflow(
        workflow=workflow,
        workflow_result=result,
        evaluators=evals,
    )

    for r in eval_results:
        print(f"\nOverall: {r.status}")
        print(f"  Passed: {r.passed}/{r.total}")
        print(f"  Portal: {r.report_url}")

        print("\nPer-agent breakdown:")
        for agent_name, agent_eval in r.sub_results.items():
            print(f"  {agent_name}: {agent_eval.passed}/{agent_eval.total} passed")
            if agent_eval.report_url:
                print(f"    Portal: {agent_eval.report_url}")

    # =========================================================================
    # Pattern 2: Run + evaluate with multiple queries
    # =========================================================================
    # Build a fresh workflow to avoid stale session state from Pattern 1.
    # The Responses API tracks previous_response_id per session, so reusing
    # a workflow after a run would reference stale tool calls.
    workflow2 = SequentialBuilder(participants=[researcher, planner]).build()

    print()
    print("=" * 60)
    print("Pattern 2: Run + evaluate with multiple queries")
    print("=" * 60)

    eval_results = await evaluate_workflow(
        workflow=workflow2,
        queries=[
            "Plan a trip from London to Tokyo",
            "Plan a trip from New York to Rome",
        ],
        evaluators=FoundryEvals(
            client=client,
            evaluators=[FoundryEvals.RELEVANCE, FoundryEvals.TASK_ADHERENCE],
        ),
    )

    for r in eval_results:
        print(f"\nOverall: {r.status}")
        print(f"  Passed: {r.passed}/{r.total}")
        if r.report_url:
            print(f"  Portal: {r.report_url}")

        print("\nPer-agent breakdown:")
        for agent_name, agent_eval in r.sub_results.items():
            print(f"  {agent_name}: {agent_eval.passed}/{agent_eval.total} passed")
            if agent_eval.report_url:
                print(f"    Portal: {agent_eval.report_url}")


if __name__ == "__main__":
    asyncio.run(main())


"""
Sample output (with actual Azure AI Foundry project):

============================================================
Pattern 1: Post-hoc workflow evaluation
============================================================

Overall: completed
  Passed: 2/2
  Portal: https://ai.azure.com/...

Per-agent breakdown:
  researcher: 1/1 passed
  planner: 1/1 passed

============================================================
Pattern 2: Run + evaluate with multiple queries
============================================================

Overall: completed
  Passed: 4/4

Per-agent breakdown:
  researcher: 2/2 passed
  planner: 2/2 passed
"""
