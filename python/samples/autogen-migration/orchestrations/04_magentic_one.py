# Copyright (c) Microsoft. All rights reserved.
"""AutoGen MagenticOneGroupChat vs Agent Framework MagenticBuilder.

Demonstrates orchestrated multi-agent workflows with a central coordinator
managing specialized agents for complex tasks.
"""

import asyncio
import json
from typing import cast

from agent_framework import (
    AgentRunUpdateEvent,
    ChatMessage,
    MagenticOrchestratorEvent,
    MagenticProgressLedger,
    WorkflowOutputEvent,
)


async def run_autogen() -> None:
    """AutoGen's MagenticOneGroupChat for orchestrated collaboration."""
    from autogen_agentchat.agents import AssistantAgent
    from autogen_agentchat.teams import MagenticOneGroupChat
    from autogen_agentchat.ui import Console
    from autogen_ext.models.openai import OpenAIChatCompletionClient

    client = OpenAIChatCompletionClient(model="gpt-4.1-mini")

    # Create specialized agents
    researcher = AssistantAgent(
        name="researcher",
        model_client=client,
        system_message="You are a research analyst. Gather and analyze information.",
        description="Research analyst for data gathering",
        model_client_stream=True,
    )

    coder = AssistantAgent(
        name="coder",
        model_client=client,
        system_message="You are a programmer. Write code based on requirements.",
        description="Software developer for implementation",
        model_client_stream=True,
    )

    reviewer = AssistantAgent(
        name="reviewer",
        model_client=client,
        system_message="You are a code reviewer. Review code for quality and correctness.",
        description="Code reviewer for quality assurance",
        model_client_stream=True,
    )

    # Create MagenticOne team with coordinator
    team = MagenticOneGroupChat(
        participants=[researcher, coder, reviewer],
        model_client=client,  # Coordinator uses this client
        max_turns=20,
        max_stalls=3,
    )

    # Run complex task and display the conversation
    print("[AutoGen] Magentic One conversation:")
    await Console(team.run_stream(task="Research Python async patterns and write a simple example"))


async def run_agent_framework() -> None:
    """Agent Framework's MagenticBuilder for orchestrated collaboration."""
    from agent_framework import MagenticBuilder
    from agent_framework.openai import OpenAIChatClient

    client = OpenAIChatClient(model_id="gpt-4.1-mini")

    # Create specialized agents
    researcher = client.as_agent(
        name="researcher",
        instructions="You are a research analyst. Gather and analyze information.",
        description="Research analyst for data gathering",
    )

    coder = client.as_agent(
        name="coder",
        instructions="You are a programmer. Write code based on requirements.",
        description="Software developer for implementation",
    )

    reviewer = client.as_agent(
        name="reviewer",
        instructions="You are a code reviewer. Review code for quality and correctness.",
        description="Code reviewer for quality assurance",
    )

    # Create Magentic workflow
    workflow = (
        MagenticBuilder()
        .participants([researcher, coder, reviewer])
        .with_manager(
            agent=client.as_agent(
                name="magentic_manager",
                instructions="You coordinate a team to complete complex tasks efficiently.",
                description="Orchestrator for team coordination",
            ),
            max_round_count=20,
            max_stall_count=3,
            max_reset_count=1,
        )
        .build()
    )

    # Run complex task
    last_message_id: str | None = None
    output_event: WorkflowOutputEvent | None = None
    print("[Agent Framework] Magentic conversation:")
    async for event in workflow.run_stream("Research Python async patterns and write a simple example"):
        if isinstance(event, AgentRunUpdateEvent):
            message_id = event.data.message_id
            if message_id != last_message_id:
                if last_message_id is not None:
                    print("\n")
                print(f"- {event.executor_id}:", end=" ", flush=True)
                last_message_id = message_id
            print(event.data, end="", flush=True)

        elif isinstance(event, MagenticOrchestratorEvent):
            print(f"\n[Magentic Orchestrator Event] Type: {event.event_type.name}")
            if isinstance(event.data, ChatMessage):
                print(f"Please review the plan:\n{event.data.text}")
            elif isinstance(event.data, MagenticProgressLedger):
                print(f"Please review progress ledger:\n{json.dumps(event.data.to_dict(), indent=2)}")
            else:
                print(f"Unknown data type in MagenticOrchestratorEvent: {type(event.data)}")

            # Block to allow user to read the plan/progress before continuing
            # Note: this is for demonstration only and is not the recommended way to handle human interaction.
            # Please refer to `with_plan_review` for proper human interaction during planning phases.
            await asyncio.get_event_loop().run_in_executor(None, input, "Press Enter to continue...")

        elif isinstance(event, WorkflowOutputEvent):
            output_event = event

    if not output_event:
        raise RuntimeError("Workflow did not produce a final output event.")
    print("\n\nWorkflow completed!")
    print("Final Output:")
    # The output of the Magentic workflow is a list of ChatMessages with only one final message
    # generated by the orchestrator.
    output_messages = cast(list[ChatMessage], output_event.data)
    if output_messages:
        output = output_messages[-1].text
        print(output)


async def main() -> None:
    print("=" * 60)
    print("Magentic One Orchestration Comparison")
    print("=" * 60)
    print("AutoGen: MagenticOneGroupChat")
    print("Agent Framework: MagenticBuilder\n")
    await run_autogen()
    print()
    await run_agent_framework()


if __name__ == "__main__":
    asyncio.run(main())
