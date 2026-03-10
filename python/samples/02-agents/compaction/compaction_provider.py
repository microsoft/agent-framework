# Copyright (c) Microsoft. All rights reserved.

import asyncio
from dataclasses import dataclass
from typing import Any

from agent_framework import (
    Content,
    Message,
)
from agent_framework._compaction import CompactionProvider, ToolResultCompactionStrategy

"""
CompactionProvider Sample

This sample demonstrates using ``CompactionProvider`` as a context provider
that automatically applies compaction before and after each agent turn.

``CompactionProvider`` stores the compacted message history in
``session.state`` and re-applies the configured strategy on every turn.
This makes it easy to integrate compaction into any agent without
manually managing message lists.

Since this sample runs without a live LLM, it simulates multiple turns
by calling ``before_run`` and ``after_run`` directly with mock contexts.
"""


class _MockSessionContext:
    """Minimal stand-in for SessionContext."""

    def __init__(self) -> None:
        self.context_messages: dict[str, list[Message]] = {}
        self.input_messages: list[Message] = []
        self._response: Any = None

    @property
    def response(self) -> Any:
        return self._response

    def extend_messages(self, provider: Any, messages: list[Message]) -> None:
        source_id = getattr(provider, "source_id", "unknown")
        self.context_messages.setdefault(source_id, []).extend(messages)


@dataclass
class _MockResponse:
    messages: list[Message]


async def main() -> None:
    # 1. Create a CompactionProvider with ToolResultCompactionStrategy.
    strategy = ToolResultCompactionStrategy(keep_last_tool_call_groups=1)
    provider = CompactionProvider(strategy=strategy, source_id="compaction")

    # Simulated session state (in a real agent this is session.state)
    state: dict[str, Any] = {}

    # 2. Simulate Turn 1: user asks, assistant calls a tool.
    print("=== Turn 1 ===")
    turn1_ctx = _MockSessionContext()
    turn1_ctx.input_messages = [Message(role="user", text="What is the weather in London?")]
    turn1_ctx._response = _MockResponse([
        Message(
            role="assistant",
            contents=[
                Content.from_function_call(call_id="c1", name="get_weather", arguments='{"city":"London"}'),
            ],
        ),
        Message(
            role="tool",
            contents=[Content.from_function_result(call_id="c1", result="cloudy, 12°C")],
        ),
        Message(role="assistant", text="London is cloudy at 12°C."),
    ])
    await provider.after_run(agent=None, session=None, context=turn1_ctx, state=state)
    print(f"  Stored {len(state.get('_compaction_messages', []))} messages in state")

    # 3. Simulate Turn 2: user asks about another city.
    print("\n=== Turn 2 ===")
    turn2_ctx = _MockSessionContext()
    turn2_ctx.input_messages = [Message(role="user", text="And Paris?")]
    turn2_ctx._response = _MockResponse([
        Message(
            role="assistant",
            contents=[
                Content.from_function_call(call_id="c2", name="get_weather", arguments='{"city":"Paris"}'),
            ],
        ),
        Message(
            role="tool",
            contents=[Content.from_function_result(call_id="c2", result="sunny, 18°C")],
        ),
        Message(role="assistant", text="Paris is sunny at 18°C."),
    ])
    await provider.after_run(agent=None, session=None, context=turn2_ctx, state=state)
    print(f"  Stored {len(state.get('_compaction_messages', []))} messages in state")

    # 4. Before Turn 3: provider loads, compacts, and injects projected messages.
    print("\n=== Before Turn 3 ===")
    turn3_ctx = _MockSessionContext()
    await provider.before_run(agent=None, session=None, context=turn3_ctx, state=state)

    injected = turn3_ctx.context_messages.get("compaction", [])
    print(f"  Injected {len(injected)} messages into context:")
    for i, m in enumerate(injected, 1):
        text = m.text or ", ".join(c.type for c in m.contents)
        print(f"    {i:02d}. [{m.role}] {text[:80]}")

    # 5. Show collapsed vs verbatim tool groups.
    summaries = [m for m in injected if (m.text or "").startswith("[Tool calls:")]
    verbatim_tools = [m for m in injected if m.role == "tool"]
    print(f"\n  Collapsed tool groups: {len(summaries)}")
    for s in summaries:
        print(f"    → {s.text}")
    print(f"  Verbatim tool results: {len(verbatim_tools)}")


if __name__ == "__main__":
    asyncio.run(main())

"""
Sample output:
=== Turn 1 ===
  Stored 4 messages in state

=== Turn 2 ===
  Stored 8 messages in state

=== Before Turn 3 ===
  Injected 7 messages into context:
    01. [assistant] [Tool calls: get_weather]
    02. [user] What is the weather in London?
    03. [assistant] London is cloudy at 12°C.
    04. [user] And Paris?
    05. [assistant] function_call
    06. [tool] function_result
    07. [assistant] Paris is sunny at 18°C.

  Collapsed tool groups: 1
    → [Tool calls: get_weather]
  Verbatim tool results: 1
"""
