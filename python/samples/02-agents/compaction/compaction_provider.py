# Copyright (c) Microsoft. All rights reserved.

import asyncio
from collections.abc import Sequence
from typing import Any

from agent_framework import (
    Agent,
    ChatContext,
    CompactionProvider,
    InMemoryHistoryProvider,
    Message,
    SlidingWindowStrategy,
    ToolResultCompactionStrategy,
    chat_middleware,
    tool,
)
from agent_framework.openai import OpenAIChatClient
from dotenv import load_dotenv

load_dotenv()

"""
CompactionProvider with Agent Example

Demonstrates ``CompactionProvider`` as part of a real agent's context-provider
pipeline alongside ``InMemoryHistoryProvider``.

The compaction provider uses two separate strategies:

- ``before_strategy``: Applied to the loaded history before the model sees it.
  Here a ``SlidingWindowStrategy`` keeps only the last 3 message groups, so
  older turns get dropped as the conversation grows.
- ``after_strategy``: Applied to the stored history after each turn.
  Here a ``ToolResultCompactionStrategy`` collapses all but the most recent
  tool-call group into short ``[Tool results: ...]`` summaries.

A chat middleware logs the messages the model actually receives (after context
providers and compaction have run) so you can see the effect of compaction.

This sample intentionally is too aggressive in excluding content, because you can see
that the last turn actually does not have the full context any longer and is therefore
only comparing the results from Paris and Tokyo and not from London.

Run with:
    uv run samples/02-agents/compaction/compaction_provider.py
"""


@tool(approval_mode="never_require")
def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    weather_data = {
        "London": "cloudy, 12°C",
        "Paris": "sunny, 18°C",
        "Tokyo": "rainy, 22°C",
    }
    return weather_data.get(city, f"No data for {city}")


@chat_middleware
async def log_model_input(context: ChatContext, call_next: Any) -> None:
    """Chat middleware that logs the messages sent to the model (after compaction)."""
    msgs: Sequence[Message] = context.messages
    print(f"\n  Model receives {len(msgs)} messages:")
    for i, m in enumerate(msgs, 1):
        text = m.text or ", ".join(c.type for c in m.contents)
        print(f"    {i:02d}. [{m.role}] {text[:70]}")
    await call_next()


async def main() -> None:
    client = OpenAIChatClient(model_id="gpt-4o-mini")

    # History provider loads/stores conversation messages in session.state.
    # skip_excluded=True means get_messages() will omit messages that were
    # marked as excluded by the CompactionProvider's after_strategy.
    history = InMemoryHistoryProvider(skip_excluded=True)

    compaction = CompactionProvider(
        # BEFORE each turn: SlidingWindow drops older message groups from
        # the loaded context so the model's input stays bounded. With
        # keep_last_groups=3, only the 3 most recent non-system groups are
        # sent to the model — older turns are not shown to the model.
        before_strategy=SlidingWindowStrategy(keep_last_groups=3, preserve_system=True),
        # AFTER each turn: ToolResultCompaction marks older tool-call groups
        # (assistant function_call + tool result messages) as excluded and
        # inserts a short "[Tool results: ...]" summary. The original messages
        # stay in storage with _excluded=True; skip_excluded on the history
        # provider ensures they won't be loaded on the next turn.
        after_strategy=ToolResultCompactionStrategy(keep_last_tool_call_groups=1),
        history_source_id=history.source_id,
    )

    # Provider order matters:
    #   before_run: history loads → compaction trims (forward order)
    #   after_run:  compaction marks exclusions → history stores (reverse order)
    agent = Agent(
        client=client,
        name="WeatherAssistant",
        instructions="You are a helpful weather assistant. Use the get_weather tool when asked about weather.",
        tools=[get_weather],
        context_providers=[history, compaction],
        middleware=[log_model_input],
    )

    session = agent.create_session()

    queries = [
        "What is the weather in London?",
        "How about Paris?",
        "And Tokyo?",
        "Which city is the warmest?",
    ]

    for turn, query in enumerate(queries, 1):
        print(f"\n{'=' * 60}")
        print(f"Turn {turn} — User: {query}")

        # ── What is in the persistent store right now? ──
        # This shows ALL messages the history provider has accumulated,
        # including any that were marked as excluded by the after_strategy
        # on the previous turn. Messages marked ✗ are excluded and won't
        # be loaded because skip_excluded=True on the history provider.
        stored = session.state.get(history.source_id, {}).get("messages", [])
        if stored:
            excluded_count = sum(1 for m in stored if m.additional_properties.get("_excluded", False))
            print(f"\n  Stored history: {len(stored)} messages ({excluded_count} excluded)")
            for i, m in enumerate(stored, 1):
                text = m.text or ", ".join(c.type for c in m.contents)
                excluded = m.additional_properties.get("_excluded", False)
                reason = m.additional_properties.get("_exclude_reason", "")
                if excluded:
                    marker = f" ✗ ({reason})"
                elif (m.text or "").startswith("[Tool results:"):
                    marker = " ← summary"
                else:
                    marker = ""
                print(f"    {i:02d}. [{m.role}]{marker} {text[:65]}")

        # ── What the model actually sees ──
        # The chat middleware fires AFTER the full context pipeline:
        #   1. InMemoryHistoryProvider loads non-excluded stored messages
        #   2. CompactionProvider.before_strategy (SlidingWindow) drops
        #      older groups so only the last 3 non-system groups survive
        #   3. The agent prepends instructions and appends the new user input
        # So this list is shorter than what's in storage.
        result = await agent.run(query, session=session)

        # ── What happens after the turn ──
        # The agent's after_run pipeline runs in reverse provider order:
        #   1. CompactionProvider.after_strategy (ToolResultCompaction) marks
        #      older tool-call groups as excluded in the stored messages —
        #      their assistant+tool messages get ✗ and a summary is inserted
        #   2. InMemoryHistoryProvider appends the new input + response
        # On the NEXT turn, skip_excluded=True means the ✗ messages won't load.
        print(f"\n  Agent: {result.text}")

    print(f"\n{'=' * 60}")
    print("Done.")


"""
Example output:
============================================================
Turn 1 — User: What is the weather in London?

  Model receives 1 messages:
    01. [user] What is the weather in London?

  Agent: The weather in London is cloudy with a temperature of 12°C.

============================================================
Turn 2 — User: How about Paris?

  Stored history: 4 messages (0 excluded)
    01. [user] What is the weather in London?
    02. [assistant] function_call
    03. [tool] function_result
    04. [assistant] The weather in London is cloudy with a temperature of 12°C.

  Model receives 5 messages:
    01. [user] What is the weather in London?
    02. [assistant] function_call
    03. [tool] function_result
    04. [assistant] The weather in London is cloudy with a temperature of 12°C.
    05. [user] How about Paris?

  Agent: The weather in Paris is sunny with a temperature of 18°C.

============================================================
Turn 3 — User: And Tokyo?

  Stored history: 8 messages (0 excluded)
    01. [user] What is the weather in London?
    02. [assistant] function_call
    03. [tool] function_result
    04. [assistant] The weather in London is cloudy with a temperature of 12°C.
    05. [user] How about Paris?
    06. [assistant] function_call
    07. [tool] function_result
    08. [assistant] The weather in Paris is sunny with a temperature of 18°C.

  Model receives 5 messages:
    01. [assistant] The weather in London is cloudy with a temperature of 12°C.
    02. [assistant] function_call
    03. [tool] function_result
    04. [assistant] The weather in Paris is sunny with a temperature of 18°C.
    05. [user] And Tokyo?

  Agent: The weather in Tokyo is rainy with a temperature of 22°C.

============================================================
Turn 4 — User: Which city is the warmest?

  Stored history: 13 messages (3 excluded)
    01. [user] What is the weather in London?
    02. [assistant] ← summary [Tool results: get_weather: cloudy, 12°C]
    03. [assistant] ✗ (tool_result_compaction) function_call
    04. [tool] ✗ (tool_result_compaction) function_result
    05. [assistant] The weather in London is cloudy with a temperature of 12°C.
    06. [user] ✗ (tool_result_compaction) How about Paris?
    07. [assistant] function_call
    08. [tool] function_result
    09. [assistant] The weather in Paris is sunny with a temperature of 18°C.
    10. [user] And Tokyo?
    11. [assistant] function_call
    12. [tool] function_result
    13. [assistant] The weather in Tokyo is rainy with a temperature of 22°C.

  Model receives 8 messages:
    01. [assistant] function_call
    02. [tool] function_result
    03. [assistant] The weather in Paris is sunny with a temperature of 18°C.
    04. [user] And Tokyo?
    05. [assistant] function_call
    06. [tool] function_result
    07. [assistant] The weather in Tokyo is rainy with a temperature of 22°C.
    08. [user] Which city is the warmest?

  Agent: Tokyo is the warmest city with a temperature of 22°C, compared to Paris, which is at 18°C.

============================================================
Done.
"""


if __name__ == "__main__":
    asyncio.run(main())
