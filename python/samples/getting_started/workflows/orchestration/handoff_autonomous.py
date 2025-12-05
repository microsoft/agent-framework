# Copyright (c) Microsoft. All rights reserved.

import asyncio
import logging
from collections.abc import AsyncIterable
from typing import cast

from agent_framework import (
    AgentRunUpdateEvent,
    ChatAgent,
    ChatMessage,
    HandoffBuilder,
    WorkflowEvent,
    WorkflowOutputEvent,
)
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential

logging.basicConfig(level=logging.ERROR)

"""Sample: Autonomous handoff workflow with agent iteration.

This sample demonstrates `with_interaction_mode("autonomous")`, where agents continue
iterating on their task until they explicitly invoke a handoff tool. This allows
specialists to perform long-running autonomous work (research, coding, analysis)
without prematurely returning control to the coordinator or user.

Routing Pattern:
    User -> Coordinator -> Specialist (iterates N times) -> Handoff -> Final Output

Prerequisites:
    - `az login` (Azure CLI authentication)
    - Environment variables for AzureOpenAIChatClient (AZURE_OPENAI_ENDPOINT, etc.)

Key Concepts:
    - Autonomous interaction mode: agents iterate until they handoff
    - Turn limits: use `with_interaction_mode("autonomous", autonomous_turn_limit=N)` to cap total iterations
"""


def create_agents(
    chat_client: AzureOpenAIChatClient,
) -> tuple[ChatAgent, ChatAgent, ChatAgent]:
    """Create coordinator and specialists for autonomous iteration."""
    coordinator = chat_client.create_agent(
        instructions=(
            "You are a coordinator. Route user requests to either research_agent or summary_agent. "
            "Always call exactly one handoff tool with a short routing acknowledgement. "
            "If unsure, default to research_agent. Never request information yourself. "
            "After a specialist hands off back to you, provide a concise final summary and stop."
        ),
        name="coordinator",
    )

    research_agent = chat_client.create_agent(
        instructions=(
            "You are a research specialist that explores topics thoroughly. "
            "When given a research task, break it down into multiple aspects and explore each one. "
            "Continue your research across multiple responses - don't try to finish everything in one response. "
            "After each response, think about what else needs to be explored. "
            "When you have covered the topic comprehensively (at least 3-4 different aspects), "
            "call the handoff tool to return to coordinator with your findings. "
            "Keep each individual response focused on one aspect."
        ),
        name="research_agent",
    )

    summary_agent = chat_client.create_agent(
        instructions=(
            "You summarize research findings. Provide a concise, well-organized summary. "
            "When done, hand off to coordinator."
        ),
        name="summary_agent",
    )

    return coordinator, research_agent, summary_agent


async def _drain(stream: AsyncIterable[WorkflowEvent]) -> list[WorkflowEvent]:
    """Collect all events from an async stream."""
    return [event async for event in stream]


def _print_conversation(events: list[WorkflowEvent]) -> None:
    """Print the final conversation snapshot from workflow output events."""
    for event in events:
        if isinstance(event, AgentRunUpdateEvent):
            print(event.data, flush=True, end="")
        elif isinstance(event, WorkflowOutputEvent):
            conversation = cast(list[ChatMessage], event.data)
            print("\n=== Final Conversation (Autonomous with Iteration) ===")
            for message in conversation:
                speaker = message.author_name or message.role.value
                text_preview = message.text[:200] + "..." if len(message.text) > 200 else message.text
                print(f"- {speaker}: {text_preview}")
            print(f"\nTotal messages: {len(conversation)}")
            print("=====================================================")


async def main() -> None:
    """Run an autonomous handoff workflow with specialist iteration enabled."""
    chat_client = AzureOpenAIChatClient(credential=AzureCliCredential())
    coordinator, research_agent, summary_agent = create_agents(chat_client)

    # Build the workflow with autonomous mode
    # In autonomous mode, agents continue iterating until they invoke a handoff tool
    workflow = (
        HandoffBuilder(
            name="autonomous_iteration_handoff",
            participants=[coordinator, research_agent, summary_agent],
        )
        .set_coordinator(coordinator)
        .add_handoff(coordinator, [research_agent, summary_agent])
        .add_handoff(research_agent, coordinator)  # Research can hand back to coordinator
        .add_handoff(summary_agent, coordinator)
        .with_interaction_mode("autonomous", autonomous_turn_limit=15)
        .with_termination_condition(
            # Terminate after coordinator provides 5 assistant responses
            lambda conv: sum(1 for msg in conv if msg.author_name == "coordinator" and msg.role.value == "assistant")
            >= 5
        )
        .build()
    )

    initial_request = "Research the key benefits and challenges of renewable energy adoption."
    print("Initial request:", initial_request)
    print("\nExpecting multiple iterations from the research agent...\n")

    events = await _drain(workflow.run_stream(initial_request))
    _print_conversation(events)

    """
    Expected behavior:
        - Coordinator routes to research_agent.
        - Research agent iterates multiple times, exploring different aspects of renewable energy.
        - Each iteration adds to the conversation without returning to coordinator.
        - After thorough research, research_agent calls handoff to coordinator.
        - Coordinator provides final summary.

    In autonomous mode, agents continue working until they invoke a handoff tool,
    allowing the research_agent to perform 3-4+ responses before handing off.
    """


if __name__ == "__main__":
    asyncio.run(main())
