# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from itertools import count

from agent_framework import (
    Agent,
    AgentTriggeredCompactionStrategy,
    CompactionStrategy,
    Message,
    ToolResultCompactionStrategy,
    included_messages,
    tool,
)
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

load_dotenv()

"""This sample demonstrates generic agent-triggered compaction.

The agent first calls ``collect_context`` to produce a deliberately large tool
result. It then calls ``compact_context``. Before the next model call,
``ToolResultCompactionStrategy`` replaces the older context-producing tool
group with a compact summary, and the wrapper removes the completed compaction
trigger group.

Environment variables:
    FOUNDRY_PROJECT_ENDPOINT — Microsoft Foundry project endpoint.
    FOUNDRY_MODEL            — Model deployment name.

Run with:
    uv run samples/02-agents/compaction/agent_triggered_compaction_basic.py
"""


MODEL_CALLS = count(1)


@tool(approval_mode="never_require")
def collect_context(topic: str) -> str:
    """Collect intentionally verbose context for a topic."""
    return "\n".join(
        f"Exploration note {index}: {topic} should remain simple, testable, and observable." for index in range(1, 21)
    )


class InspectingCompactionStrategy:
    """Print the projected messages after applying another strategy."""

    def __init__(self, strategy: CompactionStrategy) -> None:
        self.strategy = strategy
        self.requires_client_managed_history = getattr(strategy, "requires_client_managed_history", False)

    async def __call__(self, messages: list[Message]) -> bool:
        changed = await self.strategy(messages)
        visible_messages = included_messages(messages)

        print(f"\n--- Model call {next(MODEL_CALLS)} ---")
        print(f"Visible messages: {len(visible_messages)}")
        for message in visible_messages:
            parts: list[str] = []
            for content in message.contents:
                if content.type == "text":
                    text = (content.text or "").replace("\n", " ")
                    parts.append(text[:100])
                elif content.type == "function_call":
                    parts.append(f"{content.name}({content.arguments})")
                elif content.type == "function_result":
                    result = str(content.result).replace("\n", " ")
                    parts.append(f"result={result[:100]}")
                else:
                    parts.append(content.type)
            print(f"[{message.role}] {' | '.join(parts)}")
        return changed


async def main() -> None:
    # 1. Wrap an existing strategy. The trigger does not count toward the
    #    keep-last setting, so 0 compacts every workload tool-call group.
    #    A summary remains, allowing this sample to remove the trigger too.
    triggered_compaction = AgentTriggeredCompactionStrategy(
        ToolResultCompactionStrategy(keep_last_tool_call_groups=0),
        exclude_trigger=True,
    )

    # 2. Use Foundry with store=False so Agent Framework owns the full in-run
    #    message list. Run `az login` before starting.
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
        credential=AzureCliCredential(),
    )

    # 3. Register both the ordinary context-producing tool and the explicit
    #    compaction trigger tool.
    agent = Agent(
        client=client,
        name="ResearchAgent",
        instructions=(
            "If the current context contains an assistant message starting with '[Tool results:', "
            "compaction is complete: do not call any tools and answer the user in one sentence. "
            "Otherwise, call collect_context once and then call compact_context. "
            "Do not call the tools in parallel."
        ),
        tools=[collect_context, triggered_compaction.tool],
        compaction_strategy=InspectingCompactionStrategy(triggered_compaction),
        default_options={"store": False},
    )

    # 4. The third model input contains a compact tool-result summary, but
    #    neither of the original tool-call groups.
    result = await agent.run("Identify the main implementation priorities.")
    print(f"\nAgent: {result.messages[-1].text}")


if __name__ == "__main__":
    asyncio.run(main())

"""
Example output (model wording varies):

--- Model call 1 ---
Visible messages: 1
[user] Identify the main implementation priorities.

--- Model call 2 ---
Visible messages: 3
[user] Identify the main implementation priorities.
[assistant] collect_context({"topic":"implementation priorities"})
[tool] result=Exploration note 1: implementation priorities should remain simple, testable...

--- Model call 3 ---
Visible messages: 2
[user] Identify the main implementation priorities.
[assistant] [Tool results: collect_context: Exploration note 1: implementation priorities...]

Agent: Keep the implementation simple, testable, and observable.
"""
