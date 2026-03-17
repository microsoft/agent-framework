# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os

from agent_framework import ConversationSplit, EvalItem
from agent_framework_azure_ai import FoundryEvals
from azure.ai.projects.aio import AIProjectClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()

"""
This sample demonstrates how conversation split strategies affect evaluation.

The same multi-turn conversation can be split different ways, each evaluating
a different aspect of agent behavior:

1. LAST_TURN (default) — "Was the last response good given context?"
2. FULL — "Did the whole conversation serve the original request?"
3. per_turn_items — "Was each individual response appropriate?"

Prerequisites:
- An Azure AI Foundry project with a deployed model
- Set AZURE_AI_PROJECT_ENDPOINT and AZURE_AI_MODEL_DEPLOYMENT_NAME in .env
"""

# A multi-turn conversation with tool calls that we'll evaluate three ways.
CONVERSATION = [
    # Turn 1: user asks about weather → agent calls tool → responds
    {"role": "user", "content": "What's the weather in Seattle?"},
    {
        "role": "assistant",
        "content": [
            {"type": "tool_call", "tool_call_id": "c1", "name": "get_weather", "arguments": {"location": "seattle"}}
        ],
    },
    {
        "role": "tool",
        "tool_call_id": "c1",
        "content": [{"type": "tool_result", "tool_result": "62°F, cloudy with a chance of rain"}],
    },
    {"role": "assistant", "content": "Seattle is 62°F, cloudy with a chance of rain."},
    # Turn 2: user asks about Paris → agent calls tool → responds
    {"role": "user", "content": "And Paris?"},
    {
        "role": "assistant",
        "content": [
            {"type": "tool_call", "tool_call_id": "c2", "name": "get_weather", "arguments": {"location": "paris"}}
        ],
    },
    {
        "role": "tool",
        "tool_call_id": "c2",
        "content": [{"type": "tool_result", "tool_result": "68°F, partly sunny"}],
    },
    {"role": "assistant", "content": "Paris is 68°F, partly sunny."},
    # Turn 3: user asks for comparison → agent synthesizes without tool
    {"role": "user", "content": "Can you compare them?"},
    {
        "role": "assistant",
        "content": "Seattle is cooler at 62°F with rain likely, while Paris is warmer at 68°F and partly sunny. Paris is the better choice for outdoor activities.",
    },
]

TOOL_DEFINITIONS = [
    {
        "name": "get_weather",
        "description": "Get the current weather for a location.",
        "parameters": {"type": "object", "properties": {"location": {"type": "string"}}},
    },
]


def print_split(item: EvalItem, split: ConversationSplit = ConversationSplit.LAST_TURN):
    """Print the query/response split for an EvalItem."""
    d = item.to_eval_data(split=split)
    print(f"  query_messages ({len(d['query_messages'])}):")
    for m in d["query_messages"]:
        content = m.get("content", "")
        if isinstance(content, list):
            content = content[0].get("type", str(content[0]))
        print(f"    {m['role']}: {str(content)[:70]}")
    print(f"  response_messages ({len(d['response_messages'])}):")
    for m in d["response_messages"]:
        content = m.get("content", "")
        if isinstance(content, list):
            content = content[0].get("type", str(content[0]))
        print(f"    {m['role']}: {str(content)[:70]}")


async def main():
    project_client = AIProjectClient(
        endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        credential=DefaultAzureCredential(),
    )
    deployment = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4o")

    # =========================================================================
    # Strategy 1: LAST_TURN (default)
    # "Given all context, was the last response good?"
    # =========================================================================
    print("=" * 70)
    print("Strategy 1: LAST_TURN — evaluate the final response")
    print("=" * 70)

    item = EvalItem(
        query="Can you compare them?",
        response="Seattle is cooler at 62°F with rain likely, while Paris is warmer at 68°F and partly sunny. Paris is the better choice for outdoor activities.",
        conversation=CONVERSATION,
        tool_definitions=TOOL_DEFINITIONS,
    )

    print_split(item, ConversationSplit.LAST_TURN)

    results = await FoundryEvals(
        project_client=project_client,
        model_deployment=deployment,
        evaluators=[FoundryEvals.RELEVANCE, FoundryEvals.COHERENCE],
        # conversation_split defaults to LAST_TURN
    ).evaluate([item], eval_name="Split Strategy: LAST_TURN")

    print(f"\n  Result: {results.passed}/{results.total} passed")
    print(f"  Portal: {results.report_url}")
    for ir in results.items:
        for s in ir.scores:
            print(f"    {'✓' if s.passed else '✗'} {s.name}: {s.score}")
    print()

    # =========================================================================
    # Strategy 2: FULL
    # "Given the original request, did the whole conversation serve the user?"
    # =========================================================================
    print("=" * 70)
    print("Strategy 2: FULL — evaluate the entire conversation trajectory")
    print("=" * 70)

    print_split(item, ConversationSplit.FULL)

    results = await FoundryEvals(
        project_client=project_client,
        model_deployment=deployment,
        evaluators=[FoundryEvals.RELEVANCE, FoundryEvals.COHERENCE],
        conversation_split=ConversationSplit.FULL,
    ).evaluate([item], eval_name="Split Strategy: FULL")

    print(f"\n  Result: {results.passed}/{results.total} passed")
    print(f"  Portal: {results.report_url}")
    for ir in results.items:
        for s in ir.scores:
            print(f"    {'✓' if s.passed else '✗'} {s.name}: {s.score}")
    print()

    # =========================================================================
    # Strategy 3: per_turn_items
    # "Was each individual response appropriate at that point?"
    # =========================================================================
    print("=" * 70)
    print("Strategy 3: per_turn_items — evaluate each turn independently")
    print("=" * 70)

    items = EvalItem.per_turn_items(
        CONVERSATION,
        tool_definitions=TOOL_DEFINITIONS,
    )
    print(f"  Split into {len(items)} items from {len(CONVERSATION)} messages:\n")
    for i, it in enumerate(items):
        print(f"  Turn {i + 1}: query={it.query!r}, response={it.response[:60]!r}...")
    print()

    results = await FoundryEvals(
        project_client=project_client,
        model_deployment=deployment,
        evaluators=[FoundryEvals.RELEVANCE, FoundryEvals.COHERENCE],
    ).evaluate(items, eval_name="Split Strategy: Per-Turn")

    print(f"\n  Result: {results.passed}/{results.total} passed ({len(items)} items × 2 evaluators)")
    print(f"  Portal: {results.report_url}")
    for ir in results.items:
        for s in ir.scores:
            print(f"    {'✓' if s.passed else '✗'} {s.name}: {s.score}")
    print()

    print("=" * 70)
    print("All strategies complete. Compare results in the Foundry portal.")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
