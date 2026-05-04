# Copyright (c) Microsoft. All rights reserved.

"""Mix local and cloud evaluation providers in a single evaluate_agent() call.

This sample demonstrates three patterns:
1. Local-only: Fast, API-free checks for inner-loop development.
2. Cloud-only: Full Foundry evaluators for comprehensive quality assessment.
3. Mixed: Local + Foundry evaluators in a single evaluate_agent() call.

Mixing lets you get instant local feedback (keyword presence, tool usage)
alongside deeper cloud-based quality evaluation (relevance, coherence)
in one call.

Prerequisites:
- An Azure AI Foundry project with a deployed model
- Set FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_MODEL in .env
"""

import asyncio
import os

from agent_framework import (
    Agent,
    LocalEvaluator,
    evaluate_agent,
    keyword_check,
    tool_called_check,
)
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


async def main() -> None:
    # 1. Set up the chat client
    chat_client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ.get("FOUNDRY_MODEL", "gpt-4o"),
        credential=AzureCliCredential(),
    )

    # 2. Create an agent with a tool
    agent = Agent(
        client=chat_client,
        name="weather-assistant",
        instructions="You are a helpful weather assistant. Use the get_weather tool to answer questions.",
        tools=[get_weather],
    )

    # =========================================================================
    # Pattern 1: Local evaluation only (no API calls, instant results)
    # =========================================================================
    print("=" * 60)
    print("Pattern 1: Local evaluation only")
    print("=" * 60)

    local = LocalEvaluator(
        keyword_check("weather", "seattle"),
        tool_called_check("get_weather"),
    )

    results = await evaluate_agent(
        agent=agent,
        queries=["What's the weather in Seattle?"],
        evaluators=local,
    )

    for r in results:
        print(f"Status: {r.status}")
        print(f"Results: {r.passed}/{r.total} passed")
        for check_name, counts in r.per_evaluator.items():
            print(f"  {check_name}: {counts['passed']} passed, {counts['failed']} failed")
        if r.all_passed:
            print("[PASS] All local checks passed!")
        else:
            print(f"[FAIL] Failures: {r.error}")

    # =========================================================================
    # Pattern 2: Foundry evaluation only (cloud-based quality assessment)
    # =========================================================================
    print()
    print("=" * 60)
    print("Pattern 2: Foundry evaluation only")
    print("=" * 60)

    foundry = FoundryEvals(client=chat_client)

    results = await evaluate_agent(
        agent=agent,
        queries=["What's the weather in Seattle?"],
        evaluators=foundry,
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
    # Pattern 3: Mixed — local + Foundry in one call
    # =========================================================================
    print()
    print("=" * 60)
    print("Pattern 3: Mixed local + Foundry evaluation")
    print("=" * 60)

    # Local checks: fast smoke tests
    local = LocalEvaluator(
        keyword_check("weather"),
        tool_called_check("get_weather"),
    )

    # Foundry: deep quality assessment
    foundry = FoundryEvals(client=chat_client)

    # Pass both as a list — returns one EvalResults per provider
    results = await evaluate_agent(
        agent=agent,
        queries=[
            "What's the weather in Seattle?",
            "Tell me the weather in London",
        ],
        evaluators=[local, foundry],
    )

    for r in results:
        status = "PASS" if r.all_passed else "FAIL"
        print(f"  {status} {r.provider}: {r.passed}/{r.total} passed")
        for check_name, counts in r.per_evaluator.items():
            print(f"      {check_name}: {counts['passed']}/{counts['passed'] + counts['failed']}")
        if r.report_url:
            print(f"      Portal: {r.report_url}")

    if all(r.all_passed for r in results):
        print("[PASS] All checks passed (local + Foundry)!")
    else:
        failed = [r.provider for r in results if not r.all_passed]
        print(f"[FAIL] Failed providers: {', '.join(failed)}")


if __name__ == "__main__":
    asyncio.run(main())
