# Copyright (c) Microsoft. All rights reserved.

import asyncio
import logging
from typing import cast

from agent_framework import (
    AgentRunResponseUpdate,
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

"""Sample: Autonomous handoff workflow with agent factory.

This sample demonstrates how to use participant factories in HandoffBuilder to create
agents dynamically.

Using participant factories allows you to set up proper state isolation between workflow
instances created by the same builder. This is particularly useful when you need to handle
requests or tasks in parallel with stateful participants.

Routing Pattern:
    User -> Coordinator -> Specialist (iterates N times) -> Handoff -> Final Output

Prerequisites:
    - `az login` (Azure CLI authentication)
    - Environment variables for AzureOpenAIChatClient (AZURE_OPENAI_ENDPOINT, etc.)

Key Concepts:
    - Participant factories: create agents via factory functions for isolation
"""


def create_coordinator() -> ChatAgent:
    """Factory function to create a coordinator agent instance."""
    return AzureOpenAIChatClient(credential=AzureCliCredential()).create_agent(
        instructions=(
            "You are a coordinator. You break down a user query into a research task and a summary task. "
            "Assign the two tasks to the appropriate specialists, one after the other."
        ),
        name="coordinator",
    )


def create_researcher() -> ChatAgent:
    """Factory function to create a researcher agent instance."""
    return AzureOpenAIChatClient(credential=AzureCliCredential()).create_agent(
        instructions=(
            "You are a research specialist that explores topics thoroughly on the Microsoft Learn Site."
            "When given a research task, break it down into multiple aspects and explore each one. "
            "Continue your research across multiple responses - don't try to finish everything in one "
            "response. After each response, think about what else needs to be explored. When you have "
            "covered the topic comprehensively (at least 3-4 different aspects), return control to the "
            "coordinator. Keep each individual response focused on one aspect."
        ),
        name="research_agent",
    )


def create_summarizer() -> ChatAgent:
    """Factory function to create a summarizer agent instance."""
    return AzureOpenAIChatClient(credential=AzureCliCredential()).create_agent(
        instructions=(
            "You summarize research findings. Provide a concise, well-organized summary. When done, return "
            "control to the coordinator."
        ),
        name="summary_agent",
    )


last_response_id: str | None = None


def _display_event(event: WorkflowEvent) -> None:
    """Print the final conversation snapshot from workflow output events."""
    if isinstance(event, AgentRunUpdateEvent) and event.data:
        update: AgentRunResponseUpdate = event.data
        if not update.text:
            return
        global last_response_id
        if update.response_id != last_response_id:
            last_response_id = update.response_id
            print(f"\n- {update.author_name}: ", flush=True, end="")
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
    """Run the autonomous handoff workflow with participant factories."""
    # Build the handoff workflow using participant factories
    workflow_builder = (
        HandoffBuilder(
            name="Autonomous Handoff with Participant Factories",
            participant_factories={
                "coordinator": create_coordinator,
                "researcher": create_researcher,
                "summarizer": create_summarizer,
            },
        )
        .set_coordinator("coordinator")
        .add_handoff("coordinator", ["researcher", "summarizer"])
        .add_handoff("researcher", "coordinator")  # Research can hand back to coordinator
        .add_handoff("summarizer", "coordinator")
        .with_interaction_mode("autonomous", autonomous_turn_limit=15)
        .with_termination_condition(
            # Terminate after coordinator provides 5 assistant responses
            lambda conv: sum(1 for msg in conv if msg.author_name == "coordinator" and msg.role.value == "assistant")
            >= 5
        )
    )

    workflow_a = workflow_builder.build()
    print("=== Running workflow_a ===")
    request_a = "Perform a comprehensive research on Microsoft Agent Framework."
    print("Request:", request_a)
    async for event in workflow_a.run_stream(request_a):
        _display_event(event)

    request_b = "How do I create an agent?"
    print("\n\nFollow-up Request:", request_b)
    async for event in workflow_a.run_stream(request_b):
        _display_event(event)

    workflow_b = workflow_builder.build()
    print("=== Running workflow_b ===")
    print("\n\nRequest:", request_b)
    async for event in workflow_b.run_stream(request_b):
        _display_event(event)

    """
    Expected behavior:
    - workflow_a and workflow_b maintain separate states for their participants.
    - Each workflow processes its requests independently without interference.
    - workflow_a will answer the follow-up request based on its own conversation history,
      while workflow_b will provide a general answer without prior context.
    """


if __name__ == "__main__":
    asyncio.run(main())
