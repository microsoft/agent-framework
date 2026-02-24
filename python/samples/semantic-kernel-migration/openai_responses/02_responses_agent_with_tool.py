# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "semantic-kernel",
# ]
# ///
# Run with any PEP 723 compatible runner, e.g.:
#   uv run samples/semantic-kernel-migration/openai_responses/02_responses_agent_with_tool.py

# Copyright (c) Microsoft. All rights reserved.
"""Attach a lightweight function tool to the Responses API in SK and AF."""

import asyncio

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


async def run_semantic_kernel() -> None:
    from semantic_kernel.agents import OpenAIResponsesAgent
    from semantic_kernel.connectors.ai.open_ai import OpenAISettings
    from semantic_kernel.functions import kernel_function

    class MathPlugin:
        @kernel_function(name="add", description="Add two numbers")
        def add(self, a: float, b: float) -> float:
            return a + b

    client = OpenAIResponsesAgent.create_client()
    # Plugins advertise callable tools to the Responses agent.
    agent = OpenAIResponsesAgent(
        ai_model_id=OpenAISettings().responses_model_id,
        client=client,
        instructions="Use the add tool when math is required.",
        name="MathExpert",
        plugins=[MathPlugin()],
    )
    response = await agent.get_response("Use add(41, 1) and explain the result.")
    print("[SK]", response.message.content)


async def run_agent_framework() -> None:
    from agent_framework import Agent, tool
    from agent_framework.openai import OpenAIResponsesClient

    @tool(name="add", description="Add two numbers")
    async def add(a: float, b: float) -> float:
        return a + b

    chat_agent = Agent(
        client=OpenAIResponsesClient(),
        instructions="Use the add tool when math is required.",
        name="MathExpert",
        # AF registers the async function as a tool at construction.
        tools=[add],
    )
    reply = await chat_agent.run("Use add(41, 1) and explain the result.")
    print("[AF]", reply.text)


async def main() -> None:
    await run_semantic_kernel()
    await run_agent_framework()


if __name__ == "__main__":
    asyncio.run(main())
