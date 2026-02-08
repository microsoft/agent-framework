# Copyright (c) Microsoft. All rights reserved.
"""Basic AutoGen AssistantAgent vs Agent Framework ChatAgent.

Both samples expect OpenAI-compatible environment variables (OPENAI_API_KEY or
Azure OpenAI configuration). Update the prompts or client wiring to match your
model of choice before running.
"""

import asyncio


async def run_autogen() -> None:
    """Call AutoGen's AssistantAgent for a simple question."""
    from autogen_agentchat.agents import AssistantAgent
    from autogen_ext.models.openai import OpenAIChatCompletionClient

    # AutoGen agent with OpenAI model client
    client = OpenAIChatCompletionClient(model="gpt-4.1-mini")
    agent = AssistantAgent(
        name="assistant",
        model_client=client,
        system_message="You are a helpful assistant. Answer in one sentence.",
    )

    # Run the agent (AutoGen maintains conversation state internally)
    result = await agent.run(task="What is the capital of France?")
    print("[AutoGen]", result.messages[-1].to_text())


async def run_agent_framework() -> None:
    """Call Agent Framework's ChatAgent created from OpenAIChatClient."""
    from agent_framework.openai import OpenAIChatClient

    # AF constructs a lightweight ChatAgent backed by OpenAIChatClient
    client = OpenAIChatClient(model_id="gpt-4.1-mini")
    agent = client.as_agent(
        name="assistant",
        instructions="You are a helpful assistant. Answer in one sentence.",
    )

    # Run the agent (AF agents are stateless by default)
    result = await agent.run("What is the capital of France?")
    print("[Agent Framework]", result.text)


async def main() -> None:
    print("=" * 60)
    print("Basic Assistant Agent Comparison")
    print("=" * 60)
    await run_autogen()
    print()
    await run_agent_framework()


if __name__ == "__main__":
    asyncio.run(main())
