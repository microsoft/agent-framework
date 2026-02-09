# Copyright (c) Microsoft. All rights reserved.

import asyncio
import logging
from typing import cast

from agent_framework import (
    AgentResponseUpdate,
    ChatAgent,
    ChatMessage,
    resolve_agent_id,
)
from agent_framework.azure import AzureOpenAIChatClient
from agent_framework.orchestrations import HandoffBuilder
from azure.identity import AzureCliCredential

logging.basicConfig(level=logging.ERROR)

"""Sample: Autonomous handoff workflow with agent iteration.

This sample demonstrates `.with_autonomous_mode()`, where agents continue
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
    - Turn limits: use `.with_autonomous_mode(turn_limits={agent_name: N})` to cap iterations per agent
"""


def create_agents(
    chat_client: AzureOpenAIChatClient,
) -> tuple[ChatAgent, ChatAgent, ChatAgent]:
    """Create coordinator and specialists for autonomous iteration."""
    coordinator = chat_client.as_agent(
        instructions=(
            "You are a coordinator. You break down a user query into a research task and a summary task. "
            "Assign the two tasks to the appropriate specialists, one after the other."
        ),
        name="coordinator",
    )

    research_agent = chat_client.as_agent(
        instructions=(
            "You are a research specialist that explores topics thoroughly using web search. "
            "When given a research task, break it down into multiple aspects and explore each one. "
            "Continue your research across multiple responses - don't try to finish everything in one "
            "response. After each response, think about what else needs to be explored. When you have "
            "covered the topic comprehensively (at least 3-4 different aspects), return control to the "
            "coordinator. Keep each individual response focused on one aspect."
        ),
        name="research_agent",
    )

    summary_agent = chat_client.as_agent(
        instructions=(
            "You summarize research findings. Provide a concise, well-organized summary. When done, return "
            "control to the coordinator."
        ),
        name="summary_agent",
    )

    return coordinator, research_agent, summary_agent


async def main() -> None:
    """Run an autonomous handoff workflow with specialist iteration enabled."""
    chat_client = AzureOpenAIChatClient(credential=AzureCliCredential())
    coordinator, research_agent, summary_agent = create_agents(chat_client)

    # Build the workflow with autonomous mode
    # In autonomous mode, agents continue iterating until they invoke a handoff tool
    # termination_condition: Terminate after coordinator provides 5 assistant responses
    workflow = (
        HandoffBuilder(
            name="autonomous_iteration_handoff",
            participants=[coordinator, research_agent, summary_agent],
            termination_condition=lambda conv: sum(
                1 for msg in conv if msg.author_name == "coordinator" and msg.role == "assistant"
            )
            >= 5,
        )
        .with_start_agent(coordinator)
        .add_handoff(coordinator, [research_agent, summary_agent])
        .add_handoff(research_agent, [coordinator])  # Research can hand back to coordinator
        .add_handoff(summary_agent, [coordinator])
        .with_autonomous_mode(
            # You can set turn limits per agent to allow some agents to go longer.
            # If a limit is not set, the agent will get an default limit: 50.
            # Internally, handoff prefers agent names as the agent identifiers if set.
            # Otherwise, it falls back to agent IDs.
            turn_limits={
                resolve_agent_id(coordinator): 5,
                resolve_agent_id(research_agent): 10,
                resolve_agent_id(summary_agent): 5,
            }
        )
        .build()
    )

    request = "Perform a comprehensive research on Microsoft Agent Framework."
    print("Request:", request)

    last_response_id: str | None = None
    async for event in workflow.run(request, stream=True):
        if event.type == "handoff_sent":
            print(f"\nHandoff Event: from {event.data.source} to {event.data.target}\n")
        elif event.type == "output":
            data = event.data
            if isinstance(data, AgentResponseUpdate):
                if not data.text:
                    # Skip updates that don't have text content
                    # These can be tool calls or other non-text events
                    continue
                rid = data.response_id
                if rid != last_response_id:
                    if last_response_id is not None:
                        print("\n")
                    print(f"{data.author_name}:", end=" ", flush=True)
                    last_response_id = rid
                print(data.text, end="", flush=True)
            elif event.type == "output":
                # The output of the handoff workflow is a collection of chat messages from all participants
                outputs = cast(list[ChatMessage], event.data)
                print("\n" + "=" * 80)
                print("\nFinal Conversation Transcript:\n")
                for message in outputs:
                    print(f"{message.author_name or message.role}: {message.text}\n")

    """
    Expected behavior:
        - Coordinator routes to research_agent.
        - Research agent iterates multiple times, exploring different aspects of Microsoft Agent Framework.
        - Each iteration adds to the conversation without returning to coordinator.
        - After thorough research, research_agent calls handoff to coordinator.
        - Coordinator routes to summary_agent for final summary.

    In autonomous mode, agents continue working until they invoke a handoff tool,
    allowing the research_agent to perform 3-4+ responses before handing off.
    """


if __name__ == "__main__":
    asyncio.run(main())
