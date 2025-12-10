# Copyright (c) Microsoft. All rights reserved.
"""AutoGen RoundRobinGroupChat vs Agent Framework GroupChatBuilder/SequentialBuilder.

Demonstrates sequential agent orchestration where agents take turns processing
the task in a round-robin fashion.
"""

import asyncio


async def run_autogen() -> None:
    """AutoGen's RoundRobinGroupChat for sequential agent orchestration."""
    from autogen_agentchat.agents import AssistantAgent
    from autogen_agentchat.conditions import TextMentionTermination
    from autogen_agentchat.teams import RoundRobinGroupChat
    from autogen_agentchat.ui import Console
    from autogen_ext.models.openai import OpenAIChatCompletionClient

    client = OpenAIChatCompletionClient(model="gpt-4.1-mini")

    # Create specialized agents
    researcher = AssistantAgent(
        name="researcher",
        model_client=client,
        system_message="You are a researcher. Provide facts and data about the topic.",
        model_client_stream=True,
    )

    writer = AssistantAgent(
        name="writer",
        model_client=client,
        system_message="You are a writer. Turn research into engaging content.",
        model_client_stream=True,
    )

    editor = AssistantAgent(
        name="editor",
        model_client=client,
        system_message="You are an editor. Review and finalize the content. End with APPROVED if satisfied.",
        model_client_stream=True,
    )

    # Create round-robin team
    team = RoundRobinGroupChat(
        participants=[researcher, writer, editor],
        termination_condition=TextMentionTermination("APPROVED"),
    )

    # Run the team and display the conversation.
    print("[AutoGen] Round-robin conversation:")
    await Console(team.run_stream(task="Create a brief summary about electric vehicles"))


async def run_agent_framework() -> None:
    """Agent Framework's SequentialBuilder for sequential agent orchestration."""
    from agent_framework import AgentRunUpdateEvent, SequentialBuilder
    from agent_framework.openai import OpenAIChatClient

    client = OpenAIChatClient(model_id="gpt-4.1-mini")

    # Create specialized agents
    researcher = client.create_agent(
        name="researcher",
        instructions="You are a researcher. Provide facts and data about the topic.",
    )

    writer = client.create_agent(
        name="writer",
        instructions="You are a writer. Turn research into engaging content.",
    )

    editor = client.create_agent(
        name="editor",
        instructions="You are an editor. Review and finalize the content.",
    )

    # Create sequential workflow
    workflow = SequentialBuilder().participants([researcher, writer, editor]).build()

    # Run the workflow
    print("[Agent Framework] Sequential conversation:")
    current_executor = None
    async for event in workflow.run_stream("Create a brief summary about electric vehicles"):
        if isinstance(event, AgentRunUpdateEvent):
            # Print executor name header when switching to a new agent
            if current_executor != event.executor_id:
                if current_executor is not None:
                    print()  # Newline after previous agent's message
                print(f"---------- {event.executor_id} ----------")
                current_executor = event.executor_id
            if event.data:
                print(event.data.text, end="", flush=True)
    print()  # Final newline after conversation


async def run_agent_framework_with_cycle() -> None:
    """Agent Framework's WorkflowBuilder with cyclic edges and conditional exit."""
    from agent_framework import (
        AgentExecutorRequest,
        AgentExecutorResponse,
        AgentRunUpdateEvent,
        WorkflowBuilder,
        WorkflowContext,
        WorkflowOutputEvent,
        executor,
    )
    from agent_framework.openai import OpenAIChatClient

    client = OpenAIChatClient(model_id="gpt-4.1-mini")

    # Create specialized agents
    researcher = client.create_agent(
        name="researcher",
        instructions="You are a researcher. Provide facts and data about the topic.",
    )

    writer = client.create_agent(
        name="writer",
        instructions="You are a writer. Turn research into engaging content.",
    )

    editor = client.create_agent(
        name="editor",
        instructions="You are an editor. Review and finalize the content. End with APPROVED if satisfied.",
    )

    # Create custom executor for checking approval
    @executor
    async def check_approval(
        response: AgentExecutorResponse, context: WorkflowContext[AgentExecutorRequest, str]
    ) -> None:
        assert response.full_conversation is not None
        last_message = response.full_conversation[-1]
        if last_message and "APPROVED" in last_message.text:
            await context.yield_output("Content approved.")
        else:
            await context.send_message(AgentExecutorRequest(messages=response.full_conversation, should_respond=True))

    workflow = (
        WorkflowBuilder()
        .add_edge(researcher, writer)
        .add_edge(writer, editor)
        .add_edge(
            editor,
            check_approval,
        )
        .add_edge(check_approval, researcher)
        .set_start_executor(researcher)
        .build()
    )

    # Run the workflow
    print("[Agent Framework with Cycle] Cyclic conversation:")
    current_executor = None
    async for event in workflow.run_stream("Create a brief summary about electric vehicles"):
        if isinstance(event, WorkflowOutputEvent):
            print("\n---------- Workflow Output ----------")
            print(event.data)
        elif isinstance(event, AgentRunUpdateEvent):
            # Print executor name header when switching to a new agent
            if current_executor != event.executor_id:
                if current_executor is not None:
                    print()  # Newline after previous agent's message
                print(f"---------- {event.executor_id} ----------")
                current_executor = event.executor_id
            if event.data:
                print(event.data.text, end="", flush=True)
    print()  # Final newline after conversation


async def main() -> None:
    print("=" * 60)
    print("Round-Robin / Sequential Orchestration Comparison")
    print("=" * 60)
    print("AutoGen: RoundRobinGroupChat")
    print("Agent Framework: SequentialBuilder + WorkflowBuilder with cycles\n")
    await run_autogen()
    print()
    await run_agent_framework()
    print()
    await run_agent_framework_with_cycle()


if __name__ == "__main__":
    asyncio.run(main())
