# Copyright (c) Microsoft. All rights reserved.
"""AutoGen vs Agent Framework: Agent-as-a-Tool pattern.

Demonstrates hierarchical agent architectures where one agent delegates
work to specialized sub-agents wrapped as tools.
"""

import asyncio


async def run_autogen() -> None:
    """AutoGen's AgentTool for hierarchical agents with streaming."""
    from autogen_agentchat.agents import AssistantAgent
    from autogen_agentchat.tools import AgentTool
    from autogen_agentchat.ui import Console
    from autogen_ext.models.openai import OpenAIChatCompletionClient

    # Create a specialized writer agent
    writer_client = OpenAIChatCompletionClient(model="gpt-4.1-mini")
    writer = AssistantAgent(
        name="writer",
        model_client=writer_client,
        system_message="You are a creative writer. Write short, engaging content.",
        model_client_stream=True,
    )

    # Wrap writer agent as a tool (description is taken from agent.description)
    writer_tool = AgentTool(agent=writer)

    # Create coordinator agent with writer as a tool
    # IMPORTANT: Disable parallel_tool_calls when using AgentTool
    coordinator_client = OpenAIChatCompletionClient(
        model="gpt-4.1-mini",
        parallel_tool_calls=False,
    )
    coordinator = AssistantAgent(
        name="coordinator",
        model_client=coordinator_client,
        tools=[writer_tool],
        system_message="You coordinate with specialized agents. Delegate writing tasks to the writer agent.",
        model_client_stream=True,
    )

    # Run coordinator with streaming - it will delegate to writer
    print("[AutoGen]")
    await Console(coordinator.run_stream(task="Create a tagline for a coffee shop"))


async def run_agent_framework() -> None:
    """Agent Framework's as_tool() for hierarchical agents with streaming."""
    from agent_framework import FunctionCallContent, FunctionResultContent
    from agent_framework.openai import OpenAIChatClient

    client = OpenAIChatClient(model_id="gpt-4.1-mini")

    # Create specialized writer agent
    writer = client.create_agent(
        name="writer",
        instructions="You are a creative writer. Write short, engaging content.",
    )

    # Convert writer to a tool using as_tool()
    writer_tool = writer.as_tool(
        name="creative_writer",
        description="Generate creative content",
        arg_name="request",
        arg_description="What to write",
    )

    # Create coordinator agent with writer tool
    coordinator = client.create_agent(
        name="coordinator",
        instructions="You coordinate with specialized agents. Delegate writing tasks to the writer agent.",
        tools=[writer_tool],
    )

    # Run coordinator with streaming - it will delegate to writer
    print("[Agent Framework]")

    # Track accumulated function calls (they stream in incrementally)
    accumulated_calls: dict[str, FunctionCallContent] = {}

    async for chunk in coordinator.run_stream("Create a tagline for a coffee shop"):
        # Stream text tokens
        if chunk.text:
            print(chunk.text, end="", flush=True)

        # Process streaming function calls and results
        if chunk.contents:
            for content in chunk.contents:
                if isinstance(content, FunctionCallContent):
                    # Accumulate function call content as it streams in
                    call_id = content.call_id
                    if call_id in accumulated_calls:
                        # Add to existing call (arguments stream in gradually)
                        accumulated_calls[call_id] = accumulated_calls[call_id] + content
                    else:
                        # First chunk of this function call
                        accumulated_calls[call_id] = content
                        print("\n[Function Call - streaming]", flush=True)
                        print(f"  Call ID: {call_id}", flush=True)
                        print(f"  Name: {content.name}", flush=True)

                    # Show accumulated arguments so far
                    current_args = accumulated_calls[call_id].arguments
                    print(f"  Arguments: {current_args}", flush=True)

                elif isinstance(content, FunctionResultContent):
                    # Tool result - shows writer's response
                    result_text = content.result if isinstance(content.result, str) else str(content.result)
                    if result_text.strip():
                        print("\n[Function Result]", flush=True)
                        print(f"  Call ID: {content.call_id}", flush=True)
                        print(f"  Result: {result_text[:150]}{'...' if len(result_text) > 150 else ''}", flush=True)
    print()


async def main() -> None:
    print("=" * 60)
    print("Agent-as-Tool Pattern Comparison")
    print("=" * 60)
    print("Note: AutoGen requires parallel_tool_calls=False for AgentTool")
    print("      Agent Framework handles this automatically\n")
    await run_autogen()
    print()
    await run_agent_framework()


if __name__ == "__main__":
    asyncio.run(main())
