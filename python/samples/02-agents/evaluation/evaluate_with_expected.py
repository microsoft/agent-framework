# Copyright (c) Microsoft. All rights reserved.

"""Evaluate an agent with expected outputs and tool call checks.

Demonstrates ground-truth comparison and tool usage evaluation:
1. Provide expected outputs alongside queries
2. Use built-in tool_calls_present for tool verification
3. Combine multiple evaluation criteria

Usage:
    uv run python samples/02-agents/evaluation/evaluate_with_expected.py
"""

import asyncio
import os

from agent_framework import (
    Agent,
    LocalEvaluator,
    evaluate_agent,
    evaluator,
    tool_calls_present,
)
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

load_dotenv()


@evaluator
def response_matches_expected(response: str, expected_output: str) -> float:
    """Score based on word overlap with expected output."""
    if not expected_output:
        return 1.0
    response_words = set(response.lower().split())
    expected_words = set(expected_output.lower().split())
    return len(response_words & expected_words) / max(len(expected_words), 1)


async def main() -> None:
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ.get("FOUNDRY_MODEL", "gpt-4o"),
        credential=AzureCliCredential(),
    )

    agent = Agent(
        client=client,
        name="math-tutor",
        instructions="You are a math tutor. Answer concisely.",
    )

    local = LocalEvaluator(
        response_matches_expected,
        tool_calls_present,  # verifies expected tools were called
    )

    results = await evaluate_agent(
        agent=agent,
        queries=["What is 2 + 2?", "What is the square root of 144?"],
        expected_output=["4", "12"],
        evaluators=local,
    )

    for r in results:
        print(f"{r.provider}: {r.passed}/{r.total} passed")
        for item in r.items:
            print(f"  [{item.status}] {item.input_text} -> {item.output_text[:80]}")


if __name__ == "__main__":
    asyncio.run(main())
