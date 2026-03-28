# Copyright (c) Microsoft. All rights reserved.

import asyncio
from typing import Any

from agent_framework import (
    CharacterEstimatorTokenizer,
    ChatResponse,
    Content,
    Message,
    SelectiveToolCallCompactionStrategy,
    SlidingWindowStrategy,
    SummarizationStrategy,
    TokenBudgetComposedStrategy,
    ToolResultCompactionStrategy,
    TruncationStrategy,
    apply_compaction,
)

"""This sample demonstrates selecting one compaction strategy at a time.

How to use this sample:
- Keep one ``selected_strategy`` block active in ``main``.
- Comment the active block and uncomment one of the alternatives to switch strategies.
- Run again to compare behavior against the same "before" message list shown once.
"""

SUMMARY_OF_MESSAGE_IDS_KEY = "_summary_of_message_ids"
SUMMARIZED_BY_SUMMARY_ID_KEY = "_summarized_by_summary_id"

# Keep optional strategy classes imported for quick uncomment/switch in main().
AVAILABLE_STRATEGY_TYPES = (
    TruncationStrategy,
    CharacterEstimatorTokenizer,
    SlidingWindowStrategy,
    SelectiveToolCallCompactionStrategy,
    ToolResultCompactionStrategy,
    SummarizationStrategy,
    TokenBudgetComposedStrategy,
)


class LocalSummaryClient:
    """Simple local summarizer compatible with SupportsChatGetResponse."""

    async def get_response(
        self,
        messages: list[Message],
        *,
        stream: bool = False,
        options: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ChatResponse:
        return ChatResponse(messages=[Message(role="assistant", text=f"Summary for {len(messages)} messages.")])


async def main() -> None:
    # 1. Build one baseline history and print it once.
    messages = [
        Message(role="system", text="You are a helpful assistant."),
        Message(role="user", text="Plan a data migration."),
        Message(role="assistant", text="I will gather requirements."),
        Message(
            role="assistant",
            contents=[
                Content.from_function_call(
                    call_id="call_1",
                    name="list_tables",
                    arguments='{"db":"legacy"}',
                )
            ],
        ),
        Message(
            role="tool",
            contents=[
                Content.from_function_result(
                    call_id="call_1",
                    result="users, orders, events",
                )
            ],
        ),
        Message(role="assistant", text="I found three core tables."),
        Message(role="user", text="Estimate effort and risks."),
        Message(role="assistant", text="Primary risk is schema drift."),
    ]
    print("\n--- Before compaction ---")
    print(f"Message count: {len(messages)}")
    for index, message in enumerate(messages, start=1):
        message_text = message.text or ", ".join(content.type for content in message.contents)
        print(f"{index:02d}. [{message.role}] {message_text}")

    # 2. Select exactly one strategy (default shown below).
    # Truncate when included history exceeds 5 messages, then keep 4.
    # System remains anchored, so the oldest non-system messages are removed first.
    # selected_strategy_name = "TruncationStrategy"
    # selected_strategy = TruncationStrategy(max_n=5, compact_to=4, preserve_system=True)

    # Keep the most recent 4 non-system groups and preserve the system anchor.
    # A group represents a user turn (and related assistant/tool follow-up).
    # selected_strategy_name = "SlidingWindowStrategy"
    # selected_strategy = SlidingWindowStrategy(keep_last_groups=4, preserve_system=True)

    # This means all tool-call groups are removed (assistant function_call message
    # plus matching tool result messages). In this example, setting to 0 removes
    # the single assistant+tool pair.
    selected_strategy_name = "SelectiveToolCallCompactionStrategy"
    selected_strategy = SelectiveToolCallCompactionStrategy(keep_last_tool_call_groups=0)

    # Collapse older tool-call groups into short "[Tool results: tool_name]" summaries
    # while keeping the most recent group verbatim. Unlike SelectiveToolCallCompactionStrategy
    # which fully excludes groups, this preserves a readable trace of tool usage.
    # selected_strategy_name = "ToolResultCompactionStrategy"
    # selected_strategy = ToolResultCompactionStrategy(keep_last_tool_call_groups=0)

    # Summarize older messages so only recent context remains, and attach summary
    # trace metadata linking summary -> originals and originals -> summary.
    # summary_client = LocalSummaryClient()
    # selected_strategy_name = "SummarizationStrategy"
    # selected_strategy = SummarizationStrategy(
    #     client=summary_client, target_count=3, threshold=2
    # )

    # tokenizer = CharacterEstimatorTokenizer()
    # selected_strategy_name = "TokenBudgetComposedStrategy"
    # selected_strategy = TokenBudgetComposedStrategy(
    #     token_budget=150,
    #     tokenizer=tokenizer,
    #     strategies=[
    #         SelectiveToolCallCompactionStrategy(keep_last_tool_call_groups=0),
    #         SlidingWindowStrategy(keep_last_groups=2),
    #     ],
    # )

    # 3. Apply the selected strategy and print projected output.
    projected = await apply_compaction(messages, strategy=selected_strategy)
    print(f"\n--- After compaction ({selected_strategy_name}) ---")
    print(f"Message count: {len(projected)}")
    for index, message in enumerate(projected, start=1):
        message_text = message.text or ", ".join(content.type for content in message.contents)
        print(f"{index:02d}. [{message.role}] {message_text}")

    summaries = []
    summarized = []
    for message in messages:
        group_annotation = message.additional_properties.get("_group")
        if not isinstance(group_annotation, dict):
            continue
        if group_annotation.get(SUMMARY_OF_MESSAGE_IDS_KEY):
            summaries.append(message)
        if group_annotation.get(SUMMARIZED_BY_SUMMARY_ID_KEY):
            summarized.append(message)
    if summaries or summarized:
        print("Summary trace metadata present:")
        for message in summaries:
            group_annotation = message.additional_properties.get("_group")
            summarized_ids = (
                group_annotation.get(SUMMARY_OF_MESSAGE_IDS_KEY) if isinstance(group_annotation, dict) else None
            )
            print(f"  summary_id={message.message_id} summarizes={summarized_ids}")
        for message in summarized:
            group_annotation = message.additional_properties.get("_group")
            summarized_by = (
                group_annotation.get(SUMMARIZED_BY_SUMMARY_ID_KEY) if isinstance(group_annotation, dict) else None
            )
            print(f"  original_id={message.message_id} summarized_by={summarized_by}")


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output (always present):
--- Before compaction ---
Message count: 8
01. [system] You are a helpful assistant.
02. [user] Plan a data migration.
03. [assistant] I will gather requirements.
04. [assistant] function_call
05. [tool] function_result
06. [assistant] I found three core tables.
07. [user] Estimate effort and risks.
08. [assistant] Primary risk is schema drift.
"""

"""
Sample output (varies based on selected strategy):
--- After compaction (TruncationStrategy) ---
Message count: 4
01. [system] You are a helpful assistant.
02. [assistant] I found three core tables.
03. [user] Estimate effort and risks.
04. [assistant] Primary risk is schema drift.

--- After compaction (SlidingWindowStrategy) ---
Message count: 6
01. [system] You are a helpful assistant.
02. [assistant] function_call
03. [tool] function_result
04. [assistant] I found three core tables.
05. [user] Estimate effort and risks.
06. [assistant] Primary risk is schema drift.

--- After compaction (SelectiveToolCallCompactionStrategy) ---
Message count: 6
01. [system] You are a helpful assistant.
02. [user] Plan a data migration.
03. [assistant] I will gather requirements.
04. [assistant] I found three core tables.
05. [user] Estimate effort and risks.
06. [assistant] Primary risk is schema drift.

--- After compaction (ToolResultCompactionStrategy) ---
Message count: 7
01. [system] You are a helpful assistant.
02. [assistant] [Tool results: list_tables]
03. [user] Plan a data migration.
04. [assistant] I will gather requirements.
05. [assistant] I found three core tables.
06. [user] Estimate effort and risks.
07. [assistant] Primary risk is schema drift.

--- After compaction (SummarizationStrategy) ---
Message count: 5
01. [system] You are a helpful assistant.
02. [assistant] Summary for 2 messages.
03. [assistant] I found three core tables.
04. [user] Estimate effort and risks.
05. [assistant] Primary risk is schema drift.
Summary trace metadata present:
  summary_id=summary_8 summarizes=['msg_1', 'msg_2', 'msg_3', 'msg_4']
  original_id=msg_1 summarized_by=summary_8
  original_id=msg_2 summarized_by=summary_8
  original_id=msg_3 summarized_by=summary_8
  original_id=msg_4 summarized_by=summary_8

--- After compaction (TokenBudgetComposedStrategy) ---
Message count: 3
01. [system] You are a helpful assistant.
02. [user] Estimate effort and risks.
03. [assistant] Primary risk is schema drift.
"""
