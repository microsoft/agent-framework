# Copyright (c) Microsoft. All rights reserved.

import asyncio

from agent_framework import (
    Content,
    Message,
    apply_compaction,
)
from agent_framework._compaction import ToolResultCompactionStrategy, annotate_message_groups

"""
Tool Result Compaction Sample

This sample demonstrates the ToolResultCompactionStrategy, which collapses
older tool-call groups into short summary messages (e.g. ``[Tool calls: get_weather]``)
while keeping the most recent tool-call groups verbatim.

This is useful when tool results are verbose (large JSON payloads, search results, etc.)
and you want to preserve a readable trace of tool usage without the token overhead.

Compare with ``SelectiveToolCallCompactionStrategy`` in ``basics.py`` which
fully excludes older tool-call groups instead of collapsing them.
"""


async def main() -> None:
    # 1. Build a conversation with two tool-call groups.
    messages = [
        Message(role="system", text="You are a helpful travel assistant."),
        Message(role="user", text="What is the weather in London and Paris?"),
        # First tool-call group: get_weather for London
        Message(
            role="assistant",
            contents=[
                Content.from_function_call(
                    call_id="call_1",
                    name="get_weather",
                    arguments='{"city": "London"}',
                )
            ],
        ),
        Message(
            role="tool",
            contents=[
                Content.from_function_result(
                    call_id="call_1",
                    result='{"temp": 12, "condition": "cloudy", "humidity": 85, "wind": "NW 15 km/h"}',
                )
            ],
        ),
        # Second tool-call group: get_weather for Paris
        Message(
            role="assistant",
            contents=[
                Content.from_function_call(
                    call_id="call_2",
                    name="get_weather",
                    arguments='{"city": "Paris"}',
                )
            ],
        ),
        Message(
            role="tool",
            contents=[
                Content.from_function_result(
                    call_id="call_2",
                    result='{"temp": 18, "condition": "sunny", "humidity": 60, "wind": "S 10 km/h"}',
                )
            ],
        ),
        Message(role="assistant", text="London is cloudy at 12°C, Paris is sunny at 18°C."),
        Message(role="user", text="Which city should I visit?"),
        Message(role="assistant", text="Paris is warmer and sunnier — great for a day out!"),
    ]

    print("--- Before compaction ---")
    print(f"Message count: {len(messages)}")
    for i, m in enumerate(messages, 1):
        text = m.text or ", ".join(c.type for c in m.contents)
        print(f"  {i:02d}. [{m.role}] {text[:80]}")

    # 2. Apply ToolResultCompactionStrategy keeping only the last tool-call group.
    strategy = ToolResultCompactionStrategy(keep_last_tool_call_groups=1)
    annotate_message_groups(messages)
    projected = await apply_compaction(messages, strategy=strategy)

    print("\n--- After ToolResultCompactionStrategy (keep_last=1) ---")
    print(f"Message count: {len(projected)}")
    for i, m in enumerate(projected, 1):
        text = m.text or ", ".join(c.type for c in m.contents)
        print(f"  {i:02d}. [{m.role}] {text[:80]}")

    # 3. Show that the first group is now a summary, second group is verbatim.
    summaries = [m for m in projected if (m.text or "").startswith("[Tool calls:")]
    print(f"\nCollapsed tool groups: {len(summaries)}")
    for s in summaries:
        print(f"  → {s.text}")

    verbatim_tools = [m for m in projected if m.role == "tool"]
    print(f"Verbatim tool results: {len(verbatim_tools)}")


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:
--- Before compaction ---
Message count: 9
  01. [system] You are a helpful travel assistant.
  02. [user] What is the weather in London and Paris?
  03. [assistant] function_call
  04. [tool] function_result
  05. [assistant] function_call
  06. [tool] function_result
  07. [assistant] London is cloudy at 12°C, Paris is sunny at 18°C.
  08. [user] Which city should I visit?
  09. [assistant] Paris is warmer and sunnier — great for a day out!

--- After ToolResultCompactionStrategy (keep_last=1) ---
Message count: 8
  01. [system] You are a helpful travel assistant.
  02. [assistant] [Tool calls: get_weather]
  03. [user] What is the weather in London and Paris?
  04. [assistant] function_call
  05. [tool] function_result
  06. [assistant] London is cloudy at 12°C, Paris is sunny at 18°C.
  07. [user] Which city should I visit?
  08. [assistant] Paris is warmer and sunnier — great for a day out!

Collapsed tool groups: 1
  → [Tool calls: get_weather]
Verbatim tool results: 1
"""
