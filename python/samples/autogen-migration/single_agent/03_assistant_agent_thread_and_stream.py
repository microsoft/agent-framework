# Copyright (c) Microsoft. All rights reserved.
"""AutoGen vs Agent Framework: Thread management and streaming responses.

Demonstrates conversation state management and streaming in both frameworks.
"""

import asyncio


async def run_autogen() -> None:
    """AutoGen agent with conversation history and streaming."""
    from autogen_agentchat.agents import AssistantAgent
    from autogen_agentchat.ui import Console
    from autogen_ext.models.openai import OpenAIChatCompletionClient

    client = OpenAIChatCompletionClient(model="gpt-4.1-mini")
    agent = AssistantAgent(
        name="assistant",
        model_client=client,
        system_message="You are a helpful math tutor.",
        model_client_stream=True,
    )

    print("[AutoGen] Conversation with history:")
    # First turn - AutoGen maintains state internally with Console for streaming
    result = await agent.run(task="What is 15 + 27?")
    print(f"  Q1: {result.messages[-1].to_text()}")

    # Second turn - agent remembers context
    result = await agent.run(task="What about that number times 2?")
    print(f"  Q2: {result.messages[-1].to_text()}")

    print("\n[AutoGen] Streaming response:")
    # Stream response with Console for token streaming
    await Console(agent.run_stream(task="Count from 1 to 5"))


async def run_agent_framework() -> None:
    """Agent Framework agent with explicit thread and streaming."""
    from agent_framework.openai import OpenAIChatClient

    client = OpenAIChatClient(model_id="gpt-4.1-mini")
    agent = client.create_agent(
        name="assistant",
        instructions="You are a helpful math tutor.",
    )

    print("[Agent Framework] Conversation with thread:")
    # Create a thread to maintain state
    thread = agent.get_new_thread()

    # First turn - pass thread to maintain history
    result1 = await agent.run("What is 15 + 27?", thread=thread)
    print(f"  Q1: {result1.text}")

    # Second turn - agent remembers context via thread
    result2 = await agent.run("What about that number times 2?", thread=thread)
    print(f"  Q2: {result2.text}")

    print("\n[Agent Framework] Streaming response:")
    # Stream response
    print("  ", end="")
    async for chunk in agent.run_stream("Count from 1 to 5"):
        if chunk.text:
            print(chunk.text, end="", flush=True)
    print()


async def main() -> None:
    print("=" * 60)
    print("Thread Management and Streaming Comparison")
    print("=" * 60)
    await run_autogen()
    print()
    await run_agent_framework()


if __name__ == "__main__":
    asyncio.run(main())
