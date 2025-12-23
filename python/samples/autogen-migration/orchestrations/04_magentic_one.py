# Copyright (c) Microsoft. All rights reserved.
"""AutoGen MagenticOneGroupChat vs Agent Framework MagenticBuilder.

Demonstrates orchestrated multi-agent workflows with a central coordinator
managing specialized agents for complex tasks.
"""

import asyncio


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
    from agent_framework import (
        MagenticAgentDeltaEvent,
        MagenticAgentMessageEvent,
        MagenticBuilder,
        MagenticFinalResultEvent,
        MagenticOrchestratorMessageEvent,
    )
    from agent_framework.openai import OpenAIChatClient

    client = OpenAIChatClient(model_id="gpt-4.1-mini")

    # Create specialized agents
    researcher = client.create_agent(
        name="researcher",
        instructions="You are a research analyst. Gather and analyze information.",
        description="Research analyst for data gathering",
    )

    coder = client.create_agent(
        name="coder",
        instructions="You are a programmer. Write code based on requirements.",
        description="Software developer for implementation",
    )

    reviewer = client.create_agent(
        name="reviewer",
        instructions="You are a code reviewer. Review code for quality and correctness.",
        description="Code reviewer for quality assurance",
    )

    # Create Magentic workflow
    workflow = (
        MagenticBuilder()
        .participants(researcher=researcher, coder=coder, reviewer=reviewer)
        .with_standard_manager(
            chat_client=client,
            max_round_count=20,
            max_stall_count=3,
            max_reset_count=1,
        )
        .build()
    )

    # Run complex task
    print("[Agent Framework] Magentic conversation:")
    last_stream_agent_id: str | None = None
    stream_line_open: bool = False

    async for event in workflow.run_stream("Research Python async patterns and write a simple example"):
        if isinstance(event, MagenticOrchestratorMessageEvent):
            if stream_line_open:
                print()
                stream_line_open = False
            print(f"---------- Orchestrator:{event.kind} ----------")
            print(getattr(event.message, "text", ""))
        elif isinstance(event, MagenticAgentDeltaEvent):
            if last_stream_agent_id != event.agent_id or not stream_line_open:
                if stream_line_open:
                    print()
                print(f"---------- {event.agent_id} ----------")
                last_stream_agent_id = event.agent_id
                stream_line_open = True
            if event.text:
                print(event.text, end="", flush=True)
        elif isinstance(event, MagenticAgentMessageEvent):
            if stream_line_open:
                print()
                stream_line_open = False
        elif isinstance(event, MagenticFinalResultEvent):
            if stream_line_open:
                print()
                stream_line_open = False
            print("---------- Final Result ----------")
            if event.message is not None:
                print(event.message.text)

    if stream_line_open:
        print()
    print()  # Final newline after conversation


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
