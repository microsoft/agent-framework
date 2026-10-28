# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from itertools import count
from textwrap import dedent

from agent_framework import (
    Agent,
    AgentTriggeredCompactionStrategy,
    CompactionStrategy,
    InlineSkill,
    Message,
    SkillFrontmatter,
    SkillsProvider,
    UnloadSkillsCompactionStrategy,
    included_messages,
)
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

load_dotenv()

"""This sample demonstrates agent-triggered in-run compaction.

The agent follows three steps in one function-calling run:

1. Call ``load_skill`` to load a planning skill.
2. Use the skill, then call ``unload_skill``.
3. Continue without the loaded skill body in model context.

``AgentTriggeredCompactionStrategy`` controls when compaction runs.
``UnloadSkillsCompactionStrategy`` controls what context is removed.
The trigger tool is registered explicitly alongside the strategy.

A small inspection wrapper prints every model input after compaction so the
skill body is visibly present after ``load_skill`` and absent after
``unload_skill``.

Environment variables:
    FOUNDRY_PROJECT_ENDPOINT — Microsoft Foundry project endpoint.
    FOUNDRY_MODEL            — Model deployment name.

Run with:
    uv run samples/02-agents/compaction/agent_triggered_compaction.py
"""


MODEL_CALLS = count(1)


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


planning_skill = InlineSkill(
    frontmatter=SkillFrontmatter(
        name="planning",
        description="Create a concise implementation plan before execution.",
    ),
    instructions=dedent("""\
        # Planning Skill

        Before implementation:
        1. Identify the required behavior.
        2. List the smallest code changes.
        3. Define the targeted validation.
    """),
)


async def main() -> None:
    # 1. Wrap the skill strategy. The wrapper automatically adopts its
    #    unload_skill trigger and exposes that single tool.
    triggered_compaction = AgentTriggeredCompactionStrategy(
        UnloadSkillsCompactionStrategy(),
    )

    # 2. Use the standard Foundry chat client. Run `az login` before starting.
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_MODEL"],
        credential=AzureCliCredential(),
    )

    # 3. The trigger tool is registered explicitly. SkillsProvider contributes
    #    load_skill, while disabling approval keeps this sample automatic.
    agent = Agent(
        client=client,
        name="PlanningAgent",
        instructions=dedent("""\
            If the current context contains a completed unload_skill result, the planning
            skill is already unloaded: do not call any tools, return the plan, and say
            that execution can begin.

            Otherwise, follow this sequence exactly:
            1. Call load_skill with skill_name="planning".
            2. Use the loaded instructions to create a concise plan.
            3. Call unload_skill with skill_name="planning".

            Do not call load_skill and unload_skill in parallel.
        """),
        tools=[triggered_compaction.tool],
        context_providers=[
            SkillsProvider(
                planning_skill,
                disable_load_skill_approval=True,
            )
        ],
        compaction_strategy=InspectingCompactionStrategy(triggered_compaction),
        default_options={"store": False},
    )

    # 4. The final model call printed by the middleware no longer contains the
    #    load_skill call or its large planning-skill result.
    result = await agent.run("Plan a small implementation, unload the planning skill, then move to execution.")
    print(f"\nAgent: {result.messages[-1].text}")


if __name__ == "__main__":
    asyncio.run(main())

"""
Example output (model wording varies):

--- Model call 1 ---
[user] Plan a small implementation, unload the planning skill, then move to execution.

--- Model call 2 ---
[user] Plan a small implementation, unload the planning skill, then move to execution.
[assistant] load_skill({"skill_name":"planning"})
[tool] result=<name>planning</name> <description>Create a concise implementation plan...

--- Model call 3 ---
Visible messages: 3
[user] Plan a small implementation, unload the planning skill, then move to execution.
[assistant] unload_skill({"skill_name":"planning"})
[tool] result=Skill(s) 'planning' will be unloaded before the next model call.

Agent: [The generated plan, followed by confirmation that execution can begin.]
"""
