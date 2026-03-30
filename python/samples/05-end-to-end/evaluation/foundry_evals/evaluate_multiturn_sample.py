# Copyright (c) Microsoft. All rights reserved.

"""Evaluate multi-turn conversations with different split strategies.

The same multi-turn conversation can be split different ways, each evaluating
a different aspect of agent behavior:

1. LAST_TURN (default) — "Was the last response good given context?"
2. FULL — "Did the whole conversation serve the original request?"
3. per_turn_items — "Was each individual response appropriate?"

Prerequisites:
- An Azure AI Foundry project with a deployed model
- Set FOUNDRY_PROJECT_ENDPOINT and AZURE_AI_MODEL_DEPLOYMENT_NAME in .env
"""

import asyncio
import os

from agent_framework import Content, ConversationSplit, EvalItem, FunctionTool, Message
from agent_framework.foundry import FoundryChatClient, FoundryEvals
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

load_dotenv()

# A multi-turn conversation with tool calls that we'll evaluate three ways.
# Uses framework Message/Content types for type-safe conversation construction.
CONVERSATION: list[Message] = [
    # Turn 1: user asks about weather -> agent calls tool -> responds
    Message("user", ["What's the weather in Seattle?"]),
    Message(
        "assistant",
        [
            Content.from_function_call("c1", "get_weather", arguments={"location": "seattle"}),
        ],
    ),
    Message(
        "tool",
        [
            Content.from_function_result("c1", result="62°F, cloudy with a chance of rain"),
        ],
    ),
    Message("assistant", ["Seattle is 62°F, cloudy with a chance of rain."]),
    # Turn 2: user asks about Paris -> agent calls tool -> responds
    Message("user", ["And Paris?"]),
    Message(
        "assistant",
        [
            Content.from_function_call("c2", "get_weather", arguments={"location": "paris"}),
        ],
    ),
    Message(
        "tool",
        [
            Content.from_function_result("c2", result="68°F, partly sunny"),
        ],
    ),
    Message("assistant", ["Paris is 68°F, partly sunny."]),
    # Turn 3: user asks for comparison -> agent synthesizes without tool
    Message("user", ["Can you compare them?"]),
    Message(
        "assistant",
        [
            (
                "Seattle is cooler at 62°F with rain likely, while Paris is warmer "
                "at 68°F and partly sunny. Paris is the better choice for outdoor activities."
            ),
        ],
    ),
]

TOOLS = [
    FunctionTool(
        name="get_weather",
        description="Get the current weather for a location.",
    ),
]


def print_split(item: EvalItem, split: ConversationSplit = ConversationSplit.LAST_TURN) -> None:
    """Print the query/response split for an EvalItem."""
    query_msgs, response_msgs = item.split_messages(split)
    print(f"  query_messages ({len(query_msgs)}):")
    for m in query_msgs:
        text = m.text or ""
        print(f"    {m.role}: {text[:70]}")
    print(f"  response_messages ({len(response_msgs)}):")
    for m in response_msgs:
        text = m.text or ""
        print(f"    {m.role}: {text[:70]}")


async def main() -> None:
    chat_client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4o"),
        credential=AzureCliCredential(),
    )

    # =========================================================================
    # Strategy 1: LAST_TURN (default)
    # "Given all context, was the last response good?"
    # =========================================================================
    print("=" * 70)
    print("Strategy 1: LAST_TURN — evaluate the final response")
    print("=" * 70)

    # EvalItem takes conversation + tools; query/response are derived via split strategy
    item = EvalItem(CONVERSATION, tools=TOOLS)

    print_split(item, ConversationSplit.LAST_TURN)

    results = await FoundryEvals(
        client=chat_client,
        evaluators=[FoundryEvals.RELEVANCE, FoundryEvals.COHERENCE],
        # conversation_split defaults to LAST_TURN
    ).evaluate([item], eval_name="Split Strategy: LAST_TURN")

    print(f"\n  Result: {results.passed}/{results.total} passed")
    print(f"  Portal: {results.report_url}")
    for ir in results.items:
        for s in ir.scores:
            print(f"    {'PASS' if s.passed else 'FAIL'} {s.name}: {s.score}")
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
        client=chat_client,
        evaluators=[FoundryEvals.RELEVANCE, FoundryEvals.COHERENCE],
        conversation_split=ConversationSplit.FULL,
    ).evaluate([item], eval_name="Split Strategy: FULL")

    print(f"\n  Result: {results.passed}/{results.total} passed")
    print(f"  Portal: {results.report_url}")
    for ir in results.items:
        for s in ir.scores:
            print(f"    {'PASS' if s.passed else 'FAIL'} {s.name}: {s.score}")
    print()

    # =========================================================================
    # Strategy 3: per_turn_items
    # "Was each individual response appropriate at that point?"
    # =========================================================================
    print("=" * 70)
    print("Strategy 3: per_turn_items — evaluate each turn independently")
    print("=" * 70)

    items = EvalItem.per_turn_items(CONVERSATION, tools=TOOLS)
    print(f"  Split into {len(items)} items from {len(CONVERSATION)} messages:\n")
    for i, it in enumerate(items):
        print(f"  Turn {i + 1}: query={it.query!r}, response={it.response[:60]!r}...")
    print()

    results = await FoundryEvals(
        client=chat_client,
        evaluators=[FoundryEvals.RELEVANCE, FoundryEvals.COHERENCE],
    ).evaluate(items, eval_name="Split Strategy: Per-Turn")

    print(f"\n  Result: {results.passed}/{results.total} passed ({len(items)} items × 2 evaluators)")
    print(f"  Portal: {results.report_url}")
    for ir in results.items:
        for s in ir.scores:
            print(f"    {'PASS' if s.passed else 'FAIL'} {s.name}: {s.score}")
    print()

    print("=" * 70)
    print("All strategies complete. Compare results in the Foundry portal.")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
