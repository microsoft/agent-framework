# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "semantic-kernel",
# ]
# ///
# Run with any PEP 723 compatible runner, e.g.:
#   uv run samples/semantic-kernel-migration/chat_completion/02_chat_completion_with_tool.py

# Copyright (c) Microsoft. All rights reserved.
"""Demonstrate SK plugins vs Agent Framework tools with a chat agent.

Configure your OpenAI or Azure OpenAI credentials before running. The example
exposes a "specials" tool that both SDKs call during the conversation.
"""

import asyncio

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


async def run_semantic_kernel() -> None:
    from semantic_kernel.agents import ChatCompletionAgent, ChatHistoryAgentThread
    from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion
    from semantic_kernel.functions import kernel_function

    class SpecialsPlugin:
        @kernel_function(name="specials", description="List daily specials")
        def specials(self) -> str:
            return "Clam chowder, Cobb salad, Chai tea"

    # SK advertises tools by attaching plugin instances at construction time.
    agent = ChatCompletionAgent(
        service=OpenAIChatCompletion(),
        name="Host",
        instructions="Answer menu questions accurately.",
        plugins=[SpecialsPlugin()],
    )
    thread = ChatHistoryAgentThread()
    response = await agent.get_response(
        messages="What soup can I order today?",
        thread=thread,
    )
    print("[SK]", response.message.content)


async def run_agent_framework() -> None:
    from agent_framework import tool
    from agent_framework.openai import OpenAIChatClient

    @tool(name="specials", description="List daily specials")
    async def specials() -> str:
        return "Clam chowder, Cobb salad, Chai tea"

    # AF tools are provided as callables on each agent instance.
    chat_agent = OpenAIChatClient().as_agent(
        name="Host",
        instructions="Answer menu questions accurately.",
        tools=[specials],
    )
    session = chat_agent.create_session()
    reply = await chat_agent.run(
        "What soup can I order today?",
        session=session,
        tool_choice="auto",
    )
    print("[AF]", reply.text)


async def main() -> None:
    await run_semantic_kernel()
    await run_agent_framework()


if __name__ == "__main__":
    asyncio.run(main())
