# Copyright (c) Microsoft. All rights reserved.

"""Evaluate an agent with local checks — no API keys needed.

Demonstrates the simplest evaluation workflow:
1. Define checks using the @evaluator decorator
2. Run evaluate_agent() which calls agent.run() under the covers
3. Assert results in CI or inspect interactively

Usage:
    uv run python samples/02-agents/evaluation/evaluate_agent.py
"""

import asyncio
import os

from agent_framework import (
    Agent,
    LocalEvaluator,
    evaluate_agent,
    evaluator,
    keyword_check,
)
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

load_dotenv()


# A custom check — parameter names determine what data you receive
@evaluator
def is_helpful(response: str) -> bool:
    """Check the response isn't empty or a refusal."""
    refusals = ["i can't", "i'm not able", "i don't know"]
    return len(response) > 10 and not any(r in response.lower() for r in refusals)


async def main() -> None:
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ.get("FOUNDRY_MODEL", "gpt-4o"),
        credential=AzureCliCredential(),
    )

    agent = Agent(
        client=client,
        name="weather-assistant",
        instructions="You are a helpful weather assistant.",
    )

    # Combine built-in and custom checks
    local = LocalEvaluator(
        keyword_check("weather"),  # response must mention "weather"
        is_helpful,  # custom check
    )

    # evaluate_agent() calls agent.run() for each query, then evaluates
    results = await evaluate_agent(
        agent=agent,
        queries=[
            "What's the weather like in Seattle?",
            "Will it rain in London tomorrow?",
            "What should I wear for 30°C weather?",
        ],
        evaluators=local,
    )

    for r in results:
        print(f"{r.provider}: {r.passed}/{r.total} passed")
        for item in r.items:
            print(f"  [{item.status}] Q: {item.input_text[:50]}  A: {item.output_text[:50]}...")
            for score in item.scores:
                print(f"    {'PASS' if score.passed else 'FAIL'} {score.name}")

    # Use in CI: will raise EvalNotPassedError if any check fails
    # results[0].raise_for_status()


if __name__ == "__main__":
    asyncio.run(main())
