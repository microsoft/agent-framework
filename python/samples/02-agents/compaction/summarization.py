# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Any, cast

from agent_framework import (
    GROUP_ANNOTATION_KEY,
    SUMMARIZED_BY_SUMMARY_ID_KEY,
    SUMMARY_OF_MESSAGE_IDS_KEY,
    Message,
    SummarizationStrategy,
    apply_compaction,
)
from agent_framework.openai import OpenAIChatClient
from dotenv import load_dotenv

load_dotenv()

"""This sample demonstrates the SummarizationStrategy directly.

Unlike SlidingWindow/Truncation strategies that simply drop older groups,
``SummarizationStrategy`` calls a real chat client to *summarize* the oldest
message groups, replaces them with a single linked summary message, and keeps
the most recent turns verbatim. This preserves long-range context (decisions,
goals, unresolved items) while bounding the prompt size.

Key components:
- SummarizationStrategy with a real OpenAIChatClient summarizer
- ``apply_compaction`` to run the strategy over a message list
- Bidirectional summary trace metadata (summary -> originals, original -> summary)

Run with:
    uv run samples/02-agents/compaction/summarization.py  # requires OPENAI_API_KEY
"""


def _annotation(message: Message) -> dict[str, Any] | None:
    annotation = message.additional_properties.get(GROUP_ANNOTATION_KEY)
    return cast("dict[str, Any]", annotation) if isinstance(annotation, dict) else None


def _build_history() -> list[Message]:
    """Build a multi-turn conversation long enough to trigger summarization."""
    return [
        Message(role="system", contents=["You are a project planning assistant."]),
        Message(role="user", contents=["We are migrating a monolith to microservices. Where do we start?"]),
        Message(
            role="assistant",
            contents=["Start by mapping bounded contexts and identifying the highest-churn modules to extract first."],
        ),
        Message(role="user", contents=["The billing module changes most often. What are the risks of extracting it?"]),
        Message(
            role="assistant",
            contents=["Main risks: distributed transactions, invoices-table ownership, and latency on hot paths."],
        ),
        Message(role="user", contents=["How should we handle the shared invoices table?"]),
        Message(
            role="assistant",
            contents=["Use the strangler-fig pattern: dual-write during transition, then make billing the owner."],
        ),
        Message(role="user", contents=["What is the most recent decision we made?"]),
        Message(role="assistant", contents=["We decided to extract billing first using the strangler-fig pattern."]),
    ]


def _print_messages(label: str, messages: list[Message]) -> None:
    print(f"\n--- {label} ---")
    print(f"Message count: {len(messages)}")
    for index, message in enumerate(messages, start=1):
        text = message.text or ", ".join(content.type for content in message.contents)
        print(f"{index:02d}. [{message.role}] {text[:90]}")


async def main() -> None:
    # 1. Create a real summarizing client. SummarizationStrategy only requires a
    #    SupportsChatGetResponse-compatible client, so any chat client works.
    summarizer = OpenAIChatClient(model="gpt-4o-mini")

    # 2. Build a conversation and show it before compaction.
    messages = _build_history()
    _print_messages("Before compaction", messages)

    # 3. Configure the strategy. It triggers once the included non-system message
    #    count exceeds ``target_count + threshold`` (here 4 + 2 = 6), summarizing
    #    the oldest groups down toward ``target_count`` while keeping recent turns.
    strategy = SummarizationStrategy(
        client=summarizer,
        target_count=4,
        threshold=2,
    )

    # 4. Apply the strategy. The oldest groups are summarized into a single
    #    assistant message; the projected list is what the model would receive.
    projected = await apply_compaction(messages, strategy=strategy)
    _print_messages("After compaction (SummarizationStrategy)", projected)

    # 5. Inspect the generated summary and its bidirectional trace metadata.
    print("\n--- Summary trace ---")
    for message in messages:
        annotation = _annotation(message)
        if annotation is None:
            continue
        summarizes = annotation.get(SUMMARY_OF_MESSAGE_IDS_KEY)
        if summarizes:
            print(f"Generated summary ({message.message_id}):")
            print(f"  {message.text}")
            print(f"  summarizes original ids: {summarizes}")
    summarized_by: dict[str | None, Any] = {}
    for message in messages:
        annotation = _annotation(message)
        if annotation is None:
            continue
        summary_id = annotation.get(SUMMARIZED_BY_SUMMARY_ID_KEY)
        if summary_id:
            summarized_by[message.message_id] = summary_id
    if summarized_by:
        print("Originals replaced by the summary:")
        for original_id, summary_id in summarized_by.items():
            print(f"  {original_id} -> {summary_id}")


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output (summary text varies because it is generated by the model):

--- Before compaction ---
Message count: 9
01. [system] You are a project planning assistant.
02. [user] We are migrating a monolith to microservices. Where do we start?
03. [assistant] Start by mapping bounded contexts and identifying the highest-churn modules to ex
04. [user] The billing module changes most often. What are the risks of extracting it?
05. [assistant] Main risks: distributed transactions, data ownership of the invoices table, and lat
06. [user] How should we handle the shared invoices table?
07. [assistant] Use the strangler-fig pattern: dual-write during transition, then make billing the
08. [user] What is the most recent decision we made?
09. [assistant] We decided to extract billing first using the strangler-fig pattern.

--- After compaction (SummarizationStrategy) ---
Message count: 6
01. [system] You are a project planning assistant.
02. [assistant] The user is migrating a monolith to microservices and decided to extract the billin
03. [user] How should we handle the shared invoices table?
04. [assistant] Use the strangler-fig pattern: dual-write during transition, then make billing the
05. [user] What is the most recent decision we made?
06. [assistant] We decided to extract billing first using the strangler-fig pattern.

--- Summary trace ---
Generated summary (summary_9):
  The user is migrating a monolith to microservices and decided to extract the billing module first...
  summarizes original ids: ['msg_1', 'msg_2', 'msg_3', 'msg_4', 'msg_5']
Originals replaced by the summary:
  msg_1 -> summary_9
  msg_2 -> summary_9
  msg_3 -> summary_9
  msg_4 -> summary_9
  msg_5 -> summary_9
"""
