# Copyright (c) Microsoft. All rights reserved.
"""Basic SK ChatCompletionAgent vs Agent Framework ChatAgent.

Both samples expect OpenAI-compatible environment variables (OPENAI_API_KEY or
Azure OpenAI configuration). Update the prompts or client wiring to match your
model of choice before running.
"""

import asyncio


async def run_semantic_kernel() -> None:
    """Call SK's ChatCompletionAgent for a simple question."""
    from semantic_kernel.agents import ChatCompletionAgent
    from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion

    # SK agent holds the thread state internally via ChatCompletionAgent.
    agent = ChatCompletionAgent(
        service=OpenAIChatCompletion(),
        name="Support",
        instructions="Answer in one sentence.",
    )
    response = await agent.get_response(messages="How do I reset my bike tire?")
    print("[SK]", response.message.content)


async def run_agent_framework() -> None:
    """Call Agent Framework's ChatAgent created from OpenAIChatClient."""
    from agent_framework.openai import OpenAIChatClient

    # AF constructs a lightweight ChatAgent backed by OpenAIChatClient.
    chat_agent = OpenAIChatClient().create_agent(
        name="Support",
        instructions="Answer in one sentence.",
    )
    reply = await chat_agent.run("How do I reset my bike tire?")
    print("[AF]", reply.text)


async def main() -> None:
    await run_semantic_kernel()
    await run_agent_framework()


if __name__ == "__main__":
    asyncio.run(main())
