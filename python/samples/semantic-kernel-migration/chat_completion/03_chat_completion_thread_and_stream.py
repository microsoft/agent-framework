# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "semantic-kernel",
# ]
# ///
# Run with any PEP 723 compatible runner, e.g.:
#   uv run samples/semantic-kernel-migration/chat_completion/03_chat_completion_thread_and_stream.py

# Copyright (c) Microsoft. All rights reserved.
"""Compare conversation threading and streaming responses for chat agents.

Both implementations reuse a conversation thread across turns and stream output
for the second turn.
"""

import asyncio

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


async def run_semantic_kernel() -> None:
    from semantic_kernel.agents import ChatCompletionAgent, ChatHistoryAgentThread
    from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion

    # SK thread object keeps the conversation history on the agent side.
    agent = ChatCompletionAgent(
        service=OpenAIChatCompletion(),
        name="Writer",
        instructions="Keep answers short and friendly.",
    )
    thread = ChatHistoryAgentThread()

    first = await agent.get_response(
        messages="Suggest a catchy headline for our product launch.",
        thread=thread,
    )
    print("[SK]", first.message.content)

    print("[SK][stream]", end=" ")
    async for update in agent.invoke_stream(
        messages="Draft a 2 sentence blurb.",
        thread=thread,
    ):
        if update.message:
            print(update.message.content, end="", flush=True)
    print()


async def run_agent_framework() -> None:
    from agent_framework.openai import OpenAIChatClient

    # AF session objects are requested explicitly from the agent.
    chat_agent = OpenAIChatClient().as_agent(
        name="Writer",
        instructions="Keep answers short and friendly.",
    )
    session = chat_agent.create_session()

    first = await chat_agent.run(
        "Suggest a catchy headline for our product launch.",
        session=session,
    )
    print("[AF]", first.text)

    print("[AF][stream]", end=" ")
    async for chunk in chat_agent.run(
        "Draft a 2 sentence blurb.",
        session=session,
        stream=True,
    ):
        if chunk.text:
            print(chunk.text, end="", flush=True)
    print()


async def main() -> None:
    await run_semantic_kernel()
    await run_agent_framework()


if __name__ == "__main__":
    asyncio.run(main())
