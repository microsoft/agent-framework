# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Any, cast

from agent_framework import (
    GROUP_ANNOTATION_KEY,
    GROUP_TOKEN_COUNT_KEY,
    SUMMARY_OF_MESSAGE_IDS_KEY,
    CharacterEstimatorTokenizer,
    Content,
    Message,
    SelectiveToolCallCompactionStrategy,
    SlidingWindowStrategy,
    SummarizationStrategy,
    TokenBudgetComposedStrategy,
    annotate_message_groups,
    apply_compaction,
    included_token_count,
)
from agent_framework.openai import OpenAIChatClient
from dotenv import load_dotenv

load_dotenv()

"""This sample demonstrates composed in-run compaction under a token budget.

A long, tool-using conversation is compacted with a single
``TokenBudgetComposedStrategy`` that runs three strategies in order until the
included-token count fits the budget:

1. ``SelectiveToolCallCompactionStrategy`` — drop older tool-call groups
   (assistant ``function_call`` + ``tool`` result messages) that are expensive
   and rarely needed verbatim once acted upon.
2. ``SummarizationStrategy`` — use a *real* chat client to summarize the oldest
   remaining turns into a single linked summary message.
3. ``SlidingWindowStrategy`` — as a final guard, keep only the most recent
   groups if the budget is still exceeded.

Key components:
- TokenBudgetComposedStrategy with ordered, escalating strategies
- A real OpenAIChatClient used as the summarizer (not a stub)
- Tool-call groups in the history so tool-call compaction is meaningful
- Token accounting before/after via a TokenizerProtocol

Run with:
    uv run samples/02-agents/compaction/advanced.py  # requires OPENAI_API_KEY
"""


def _build_long_history() -> list[Message]:
    """Build a long, tool-using migration conversation to create token pressure."""
    history: list[Message] = [
        Message(role="system", contents=["You are a migration copilot that plans and executes database migrations."]),
    ]

    # A few verbose planning turns to build up token pressure.
    for i in range(1, 5):
        history.append(
            Message(
                role="user",
                contents=[f"Iteration {i}: capture migration requirements, constraints, and edge cases in detail."],
            )
        )
        history.append(
            Message(
                role="assistant",
                contents=[
                    (
                        f"Iteration {i}: produced a detailed plan covering dependencies, rollback guidance, data "
                        "backfill, and a full testing matrix. This response is intentionally verbose to add pressure."
                    )
                ],
            )
        )

    # A tool-call group: the assistant inspects the schema via a tool.
    history.append(
        Message(
            role="assistant",
            contents=[Content.from_function_call(call_id="call_1", name="inspect_schema", arguments='{"db":"legacy"}')],
        )
    )
    history.append(
        Message(
            role="tool",
            contents=[Content.from_function_result(call_id="call_1", result="tables: users, orders, invoices, events")],
        )
    )
    history.append(Message(role="assistant", contents=["Schema inspection found four core tables to migrate."]))

    # The most recent turn — this should survive compaction verbatim.
    history.append(Message(role="user", contents=["What is the safest order to migrate these tables?"]))
    history.append(
        Message(
            role="assistant",
            contents=["Migrate reference tables (users) first, then orders, then invoices, and events last."],
        )
    )
    return history


def _annotation(message: Message) -> dict[str, Any] | None:
    annotation = message.additional_properties.get(GROUP_ANNOTATION_KEY)
    return cast("dict[str, Any]", annotation) if isinstance(annotation, dict) else None


def _token_count(message: Message) -> int | None:
    annotation = _annotation(message)
    return annotation.get(GROUP_TOKEN_COUNT_KEY) if annotation else None


def _relation(message: Message) -> str:
    """Describe how a projected message relates to the original messages."""
    annotation = _annotation(message)
    if annotation is None:
        return ""
    summarizes = annotation.get(SUMMARY_OF_MESSAGE_IDS_KEY)
    if summarizes:
        return f" <- summary of {summarizes}"
    return ""


async def main() -> None:
    # 1. Build synthetic history representing long-running, tool-using growth.
    messages = _build_long_history()

    # 2. Configure tokenizer and measure token count before compaction.
    tokenizer = CharacterEstimatorTokenizer()
    annotate_message_groups(messages, tokenizer=tokenizer)
    budget_before = included_token_count(messages)

    print("Before compaction message set:")
    for msg in messages:
        text_preview = msg.text[:80] if msg.text else "<non-text>"
        print(f"- [{msg.role}] {text_preview} ({msg.message_id}, {_token_count(msg)} tokens)")
    print()

    # 3. Create a real summarizer client. SummarizationStrategy only requires a
    #    SupportsChatGetResponse-compatible client.
    summarizer = OpenAIChatClient(model="gpt-4o-mini")

    # 4. Configure the composed strategy stack. Strategies run in order and the
    #    composed strategy stops as soon as the included-token budget is met.
    #    The budget is set high enough that the generated summary fits within it:
    #    a tighter budget would trip the composed fallback, which excludes the
    #    oldest group first (the summary) once the included set exceeds the
    #    budget. SlidingWindowStrategy remains as a recency safety net for longer
    #    histories; for this sample summarization alone reaches budget, so the
    #    window does not need to fire.
    composed = TokenBudgetComposedStrategy(
        token_budget=400,
        tokenizer=tokenizer,
        strategies=[
            SelectiveToolCallCompactionStrategy(keep_last_tool_call_groups=0),
            SummarizationStrategy(client=summarizer, target_count=3, threshold=2),
            SlidingWindowStrategy(keep_last_groups=4),
        ],
    )

    # 5. Apply compaction and inspect the budget result.
    projected = await apply_compaction(messages, strategy=composed, tokenizer=tokenizer)
    budget_after = included_token_count(messages)

    print(f"Projected messages after compaction: {len(projected)}")
    print(f"Included token count before compaction: {budget_before}")
    print(f"Included token count after compaction: {budget_after}")
    print("Projected roles:", [m.role for m in projected])
    print("Projected messages with token counts:")
    for msg in projected:
        text_preview = msg.text[:80] if msg.text else "<non-text>"
        print(f"- [{msg.role}] {text_preview} ({msg.message_id}, {_token_count(msg)} tokens){_relation(msg)}")

    # 6. Surface the model-generated summary, if summarization fired.
    for msg in messages:
        annotation = _annotation(msg)
        if annotation and annotation.get(SUMMARY_OF_MESSAGE_IDS_KEY):
            print("\nGenerated summary:")
            print(f"  {msg.text}")
            print(f"  summarizes: {annotation.get(SUMMARY_OF_MESSAGE_IDS_KEY)}")


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output (summary text and token counts vary because the summary is generated by the model):

Before compaction message set:
- [system] You are a migration copilot that plans and executes database migrations. (msg_0, 46 tokens)
- [user] Iteration 1: capture migration requirements, constraints, and edge cases in deta (msg_1, 48 tokens)
- [assistant] Iteration 1: produced a detailed plan covering dependencies, rollback guidance,  (msg_2, 73 tokens)
...
- [user] What is the safest order to migrate these tables? (msg_12, 40 tokens)
- [assistant] Migrate reference tables (users) first, then orders, then invoices, and events l (msg_13, 50 tokens)

Projected messages after compaction: 5
Included token count before compaction: 757
Included token count after compaction: 274
Projected roles: ['system', 'assistant', 'assistant', 'user', 'assistant']
Projected messages with token counts:
- [system] You are a migration copilot that plans and executes database migrations. (msg_0, 46 tokens)
- [assistant] Across four planning turns the user and assistant... (summary_14, 96 tokens) <- summary of [msg_1..8]
- [assistant] Schema inspection found four core tables to migrate. (msg_11, 42 tokens)
- [user] What is the safest order to migrate these tables? (msg_12, 40 tokens)
- [assistant] Migrate reference tables (users) first, then orders, then invoices, and events l (msg_13, 50 tokens)

Generated summary:
  Across four planning turns the user and assistant defined the migration requirements...
  summarizes: ['msg_1', 'msg_2', 'msg_3', 'msg_4', 'msg_5', 'msg_6', 'msg_7', 'msg_8']
"""
